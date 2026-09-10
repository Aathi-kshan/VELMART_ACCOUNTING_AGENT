"""audit_logs, append-only + hash chain trigger

Revision ID: 0005
Revises: 0004
Create Date: plan section 8.5 / 18.1

row_hash = sha256(prev_hash || company_id || actor_user_id || action ||
                   entity_type || entity_id || old_data || new_data ||
                   source || created_at)

Written by a Postgres BEFORE INSERT trigger, not application code, so no
code path can skip it. app_user has UPDATE/DELETE/TRUNCATE revoked on this
table (the grant that makes that revoke meaningful happens in migration
0008, once app_user has any privileges at all — see the note there); a
nightly cron job (app/tasks/audit_chain_verify.py) verifies the chain and
alerts on any break.

The trigger function is SECURITY DEFINER: `SELECT ... FOR UPDATE` (used to
serialise concurrent inserts onto one chain) requires UPDATE privilege in
Postgres even though the row is never modified, which would otherwise force
granting app_user exactly the privilege this table revokes from it. Running
the lock as the (trusted) function owner, with an explicit search_path to
close the standard SECURITY DEFINER search-path attack, keeps that privilege
out of every session app_user ever opens.
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE audit_logs (
            id            BIGSERIAL PRIMARY KEY,
            company_id    UUID NOT NULL,
            actor_user_id UUID,
            actor_role    user_role,
            action        TEXT NOT NULL,
            entity_type   TEXT NOT NULL,
            entity_id     UUID,
            page_id       UUID,
            old_data      JSONB,
            new_data      JSONB,
            diff          JSONB,
            source        TEXT NOT NULL,
            ai_session_id UUID,
            ip_address    INET,
            user_agent    TEXT,
            prev_hash     TEXT,
            row_hash      TEXT NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX ix_audit_company_time ON audit_logs (company_id, created_at DESC);")
    op.execute("CREATE INDEX ix_audit_entity ON audit_logs (entity_type, entity_id);")

    # Hash-chain trigger: locks the previous row so concurrent inserts can't
    # race and produce two rows claiming the same prev_hash.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_audit_logs_hash_chain() RETURNS trigger AS $$
        DECLARE
            v_prev_hash TEXT;
        BEGIN
            SELECT row_hash INTO v_prev_hash
            FROM audit_logs
            ORDER BY id DESC
            LIMIT 1
            FOR UPDATE;

            NEW.created_at := COALESCE(NEW.created_at, now());
            NEW.prev_hash := v_prev_hash;
            NEW.row_hash := encode(
                digest(
                    concat_ws('|',
                        COALESCE(v_prev_hash, ''),
                        NEW.company_id::text,
                        COALESCE(NEW.actor_user_id::text, ''),
                        NEW.action,
                        NEW.entity_type,
                        COALESCE(NEW.entity_id::text, ''),
                        COALESCE(NEW.old_data::text, ''),
                        COALESCE(NEW.new_data::text, ''),
                        NEW.source,
                        NEW.created_at::text
                    ),
                    'sha256'
                ),
                'hex'
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
           SECURITY DEFINER
           SET search_path = public, pg_temp;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_hash_chain
            BEFORE INSERT ON audit_logs
            FOR EACH ROW
            EXECUTE FUNCTION fn_audit_logs_hash_chain();
        """
    )

    # A no-op at this point in the chain — app_user has no privileges on
    # anything until 0008 grants them. Kept so the intent sits beside the
    # table it protects; 0008 re-applies it where it actually bites.
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM app_user;")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_hash_chain ON audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS fn_audit_logs_hash_chain();")
    op.execute("DROP TABLE IF EXISTS audit_logs;")
