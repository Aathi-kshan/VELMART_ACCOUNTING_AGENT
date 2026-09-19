"""Re-seed the audit chain head from the log, not from zero

Revision ID: 0023
Revises: 0022

Fixes a defect introduced by 0021's own fix, found by re-auditing it.

0021 made the trigger recreate `audit_chain_head` when the row was missing, so
that emptying the table could not break every audit write. It seeded the row
with `(true, NULL, 0)` — a constant. That is correct only when `audit_logs` is
*also* empty, which was the case that prompted it (the test suite truncates
both).

With the head row lost but the log intact, it is actively harmful: `last_seq`
restarts at 0, so the next insert takes `chain_seq = 1`, which already exists,
and `ux_audit_logs_chain_seq` rejects it. Every audit insert then fails — and
since every mutation writes an audit row, every mutation in the application
fails. Precisely the outcome the self-healing branch was added to prevent.

Seeding from the log instead makes the branch do what it claimed: resume the
chain where it actually left off, or start clean when there is genuinely
nothing to resume from.

**`audit_chain_head` and `audit_logs` are one unit.** Truncating the log while
keeping the head leaves a stale `prev_hash` that no later row can match, and
the verifier reports permanent tampering. Truncate both together, as
`tests/conftest.py` does.
"""

from __future__ import annotations

from alembic import op

revision = "0023"
down_revision = "0022"
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

_SEED_FROM_LOG = """
            INSERT INTO audit_chain_head (only_row, last_row_hash, last_seq)
            SELECT true,
                   (SELECT row_hash FROM audit_logs ORDER BY chain_seq DESC LIMIT 1),
                   COALESCE((SELECT max(chain_seq) FROM audit_logs), 0)
            ON CONFLICT (only_row) DO NOTHING;
"""

_SEED_FROM_ZERO = """
            INSERT INTO audit_chain_head (only_row, last_row_hash, last_seq)
            VALUES (true, NULL, 0)
            ON CONFLICT (only_row) DO NOTHING;
"""


def _trigger_sql(seed: str) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION fn_audit_logs_hash_chain() RETURNS trigger AS $$
        DECLARE
            v_prev_hash TEXT;
            v_prev_seq  BIGINT;
        BEGIN
            PERFORM pg_advisory_xact_lock({_CHAIN_LOCK_KEY});
{seed}
            SELECT last_row_hash, last_seq INTO v_prev_hash, v_prev_seq
            FROM audit_chain_head
            WHERE only_row
            FOR UPDATE;

            NEW.chain_seq := v_prev_seq + 1;
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
            SET last_row_hash = NEW.row_hash, last_seq = NEW.chain_seq, updated_at = now()
            WHERE only_row;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
           SECURITY DEFINER
           SET search_path = public, pg_temp;
    """


def upgrade() -> None:
    op.execute(_trigger_sql(_SEED_FROM_LOG))
    # Reconcile any head that is already behind the log.
    op.execute(
        """
        UPDATE audit_chain_head SET
            last_seq = COALESCE((SELECT max(chain_seq) FROM audit_logs), 0),
            last_row_hash = (SELECT row_hash FROM audit_logs ORDER BY chain_seq DESC LIMIT 1)
        WHERE only_row
          AND last_seq < COALESCE((SELECT max(chain_seq) FROM audit_logs), 0);
        """
    )


def downgrade() -> None:
    op.execute(_trigger_sql(_SEED_FROM_ZERO))
