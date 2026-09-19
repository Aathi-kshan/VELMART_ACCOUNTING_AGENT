"""Sequence the audit chain on a single head row, not on the log's tail

Revision ID: 0020
Revises: 0019

Migration 0018 replaced 0005's `SELECT ... FOR UPDATE` on the newest
`audit_logs` row with `pg_advisory_xact_lock`. That was still not enough, and
a concurrency test caught it: eight parallel record creates forked the chain
in roughly one run in eight — every request succeeding, and the verifier then
reporting the log as tampered with.

Two separate problems, both fixed here.

**0005's lock did not lock the right thing.** Locking the current tail row
does not stop another transaction inserting a *new* row: two inserts do not
conflict with each other, only with the row they both read.

**0018's advisory lock serialised the trigger but not its snapshot.** A
BEFORE INSERT trigger's `SELECT` runs under the snapshot of the statement
that fired it. So T2 could wait properly on the advisory lock, acquire it
after T1 committed, and *still* read the pre-T1 tail — because its snapshot
was taken when its own INSERT began. Serialising execution does not
re-take a snapshot.

The fix is to make every writer contend on one specific row.
`audit_chain_head` holds the current chain tip, and the trigger takes
`SELECT ... FOR UPDATE` on it. When T2 blocks on T1's lock on that row,
Postgres re-fetches the latest committed version of **that row** once T1
commits (EvalPlanQual) — which is exactly the semantics the original code
wanted and the reason a single shared row works where the moving tail did
not. This is the ordinary sequence-table pattern.

The advisory lock is kept as well: it costs one lock acquisition and makes
the ordering explicit rather than emergent from row-level contention.

`app_user` is granted nothing on the new table. The trigger is
`SECURITY DEFINER`, owned by `migrator`, so it can maintain the head without
the application role being able to rewrite the chain tip directly.
"""

from __future__ import annotations

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

_CHAIN_LOCK_KEY = 8_274_100_501

_HASHED_FIELDS = """
                        COALESCE(v_prev_hash, ''),
                        NEW.company_id::text,
                        COALESCE(NEW.actor_user_id::text, ''),
                        COALESCE(NEW.actor_role::text, ''),
                        NEW.action,
                        NEW.entity_type,
                        COALESCE(NEW.entity_id::text, ''),
                        COALESCE(NEW.page_id::text, ''),
                        COALESCE(NEW.old_data::text, ''),
                        COALESCE(NEW.new_data::text, ''),
                        COALESCE(NEW.diff::text, ''),
                        NEW.source,
                        COALESCE(NEW.ai_session_id::text, ''),
                        COALESCE(NEW.ip_address::text, ''),
                        COALESCE(NEW.user_agent, ''),
                        NEW.created_at::text
"""


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE audit_chain_head (
            only_row      BOOLEAN PRIMARY KEY DEFAULT true CHECK (only_row),
            last_row_hash TEXT,
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    # Seed from wherever the chain currently ends, so an existing log keeps
    # linking across this migration instead of restarting.
    op.execute(
        """
        INSERT INTO audit_chain_head (only_row, last_row_hash)
        VALUES (true, (SELECT row_hash FROM audit_logs ORDER BY id DESC LIMIT 1));
        """
    )
    op.execute("REVOKE ALL PRIVILEGES ON audit_chain_head FROM app_user;")
    op.execute("REVOKE ALL PRIVILEGES ON audit_chain_head FROM ai_reader;")

    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION fn_audit_logs_hash_chain() RETURNS trigger AS $$
        DECLARE
            v_prev_hash TEXT;
        BEGIN
            PERFORM pg_advisory_xact_lock({_CHAIN_LOCK_KEY});

            -- FOR UPDATE on one shared row: a blocked transaction re-reads
            -- this row's newest committed version once the holder commits.
            -- Reading the tail of audit_logs could not do that, because two
            -- inserts never conflict with one another.
            SELECT last_row_hash INTO v_prev_hash
            FROM audit_chain_head
            WHERE only_row
            FOR UPDATE;

            NEW.created_at := COALESCE(NEW.created_at, now());
            NEW.prev_hash := v_prev_hash;
            NEW.row_hash := encode(
                digest(
                    concat_ws('|',{_HASHED_FIELDS}
                    ),
                    'sha256'
                ),
                'hex'
            );

            UPDATE audit_chain_head
            SET last_row_hash = NEW.row_hash, updated_at = now()
            WHERE only_row;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
           SECURITY DEFINER
           SET search_path = public, pg_temp;
        """
    )


def downgrade() -> None:
    # Back to 0018's advisory-lock-plus-tail-read form, which is racy — see
    # the module docstring. Restored faithfully rather than improved, so the
    # downgrade genuinely returns the previous behaviour.
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION fn_audit_logs_hash_chain() RETURNS trigger AS $$
        DECLARE
            v_prev_hash TEXT;
        BEGIN
            PERFORM pg_advisory_xact_lock({_CHAIN_LOCK_KEY});

            SELECT row_hash INTO v_prev_hash
            FROM audit_logs
            ORDER BY id DESC
            LIMIT 1;

            NEW.created_at := COALESCE(NEW.created_at, now());
            NEW.prev_hash := v_prev_hash;
            NEW.row_hash := encode(
                digest(
                    concat_ws('|',{_HASHED_FIELDS}
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
    op.execute("DROP TABLE IF EXISTS audit_chain_head;")
