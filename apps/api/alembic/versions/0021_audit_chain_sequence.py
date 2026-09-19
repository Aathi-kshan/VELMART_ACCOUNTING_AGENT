"""Order the audit chain by a sequence assigned under the chain lock

Revision ID: 0021
Revises: 0020

0020 made every writer contend on one head row, which fixed *reading* a stale
predecessor. Concurrent inserts still forked the chain about one run in six,
and the reason is more subtle than the locking.

`audit_logs.id` is `BIGSERIAL`. Its value comes from the column default, which
Postgres evaluates **before** BEFORE-INSERT triggers run — so the id is already
fixed by the time the trigger acquires the chain lock. Two concurrent inserts
can therefore take their ids in one order and the lock in the other:

    T1 takes id 5, T2 takes id 6
    T2 wins the lock first  ->  prev_hash(T2) = hash(row 4)
    T1 acquires next        ->  prev_hash(T1) = hash(T2)

The chain is now perfectly well formed in *lock order* (4 -> T2 -> T1), but
`audit_chain_verify` walks it with `LAG(row_hash) OVER (ORDER BY id)`, i.e. in
*id order* (4 -> T1 -> T2), where T1's `prev_hash` matches nothing. The result
is a verifier that reports tampering because two records were written at the
same moment. That has been true since the chain was introduced in 0005; it
only became visible once a test wrote to it concurrently.

So the chain needs its own ordering, allocated where the linking happens.
`chain_seq` is assigned inside the trigger while the head row is held, which
makes "the order rows were chained in" and "the order rows are verified in"
the same thing by construction rather than by luck of scheduling.

Existing rows are backfilled in `id` order, which is the order 0018 re-hashed
them in, so history stays continuous.
"""

from __future__ import annotations

from alembic import op

revision = "0021"
down_revision = "0020"
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
    op.execute("ALTER TABLE audit_logs ADD COLUMN chain_seq BIGINT;")
    # Backfill in id order — the order 0018's re-hash already linked them in.
    op.execute(
        """
        WITH ordered AS (
            SELECT id, row_number() OVER (ORDER BY id) AS seq FROM audit_logs
        )
        UPDATE audit_logs a SET chain_seq = ordered.seq
        FROM ordered WHERE ordered.id = a.id;
        """
    )
    op.execute("ALTER TABLE audit_logs ALTER COLUMN chain_seq SET NOT NULL;")
    op.execute("CREATE UNIQUE INDEX ux_audit_logs_chain_seq ON audit_logs (chain_seq);")

    op.execute("ALTER TABLE audit_chain_head ADD COLUMN last_seq BIGINT NOT NULL DEFAULT 0;")
    op.execute(
        "UPDATE audit_chain_head SET last_seq = COALESCE((SELECT max(chain_seq) FROM audit_logs), 0);"
    )

    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION fn_audit_logs_hash_chain() RETURNS trigger AS $$
        DECLARE
            v_prev_hash TEXT;
            v_prev_seq  BIGINT;
        BEGIN
            PERFORM pg_advisory_xact_lock({_CHAIN_LOCK_KEY});

            -- Recreate the head row if it is missing, rather than letting a
            -- NULL `last_seq` become a NULL `chain_seq` and fail the insert.
            -- Without this, anything that empties the table — a TRUNCATE, a
            -- partial restore — silently breaks *every* subsequent audit
            -- write, which means breaking every mutation in the application.
            -- Safe under the advisory lock taken above.
            INSERT INTO audit_chain_head (only_row, last_row_hash, last_seq)
            VALUES (true, NULL, 0)
            ON CONFLICT (only_row) DO NOTHING;

            -- One shared row, so a blocked writer re-reads the newest
            -- committed values once the holder commits (0020).
            SELECT last_row_hash, last_seq INTO v_prev_hash, v_prev_seq
            FROM audit_chain_head
            WHERE only_row
            FOR UPDATE;

            -- Allocated here, under the lock, rather than taken from the
            -- BIGSERIAL id which Postgres assigned before this trigger ran.
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
    )


def downgrade() -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION fn_audit_logs_hash_chain() RETURNS trigger AS $$
        DECLARE
            v_prev_hash TEXT;
        BEGIN
            PERFORM pg_advisory_xact_lock({_CHAIN_LOCK_KEY});

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
    op.execute("ALTER TABLE audit_chain_head DROP COLUMN last_seq;")
    op.execute("DROP INDEX IF EXISTS ux_audit_logs_chain_seq;")
    op.execute("ALTER TABLE audit_logs DROP COLUMN chain_seq;")
