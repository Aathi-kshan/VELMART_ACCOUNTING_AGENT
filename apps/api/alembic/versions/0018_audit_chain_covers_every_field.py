"""Audit hash chain: cover every field, and serialise inserts properly

Revision ID: 0018
Revises: 0017

The chain from 0005 hashed ten fields: `prev_hash`, `company_id`,
`actor_user_id`, `action`, `entity_type`, `entity_id`, `old_data`,
`new_data`, `source`, `created_at`.

It did **not** cover `page_id`, `actor_role`, `diff`, `ai_session_id`,
`ip_address` or `user_agent`. Those are not incidental:

* `page_id` is load-bearing — `audit_read_service` filters "show me this
  page's history" on it, and a manager's audit visibility is decided by it.
  Anyone able to UPDATE the table could re-point an entry at a different page
  and the chain would still verify clean.
* `actor_role` records *who* did it, which is most of the point of an audit
  trail, and `ai_session_id` records whether the AI did.
* `ip_address` and `user_agent` are the forensic fields.

The chain is meant to make the audit log tamper-evident, so it has to cover
everything an attacker would want to change.

**Serialisation.** 0005's trigger took `SELECT ... ORDER BY id DESC LIMIT 1
FOR UPDATE` and its comment claimed that stopped two inserts racing. It does
not, under READ COMMITTED: T2's snapshot is taken before T1 commits, so T2
locks row N, waits, and after T1 commits its EvalPlanQual recheck re-evaluates
only the row it locked — still row N — and returns hash(N). Rows N+1 and N+2
then both carry `prev_hash = hash(N)`, forking the chain. The verifier reports
that as tampering, so the failure mode was a false alarm on concurrent
writes rather than silent corruption, but the chain is only useful if a
reported break means something. `pg_advisory_xact_lock` on a fixed key
serialises the insert itself, which is what was wanted.

**Existing rows are re-hashed.** Every historical row's `row_hash` is
recomputed in `id` order under the new definition. This rewrites hashes, not
data: no audited field changes, and the chain is continuous before and after.
It has to happen in the same migration as the trigger, or every pre-existing
row would fail verification against the new rule.
"""

from __future__ import annotations

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

#: Any int works as long as writer and migration agree; it only has to not
#: collide with another advisory lock in this database.
_CHAIN_LOCK_KEY = 8_274_100_501

#: The field list, shared by the trigger, the re-hash below, and
#: `app/tasks/audit_chain_verify.py`. Kept as one string so the three cannot
#: drift apart silently — that drift is exactly what this migration fixes.
_HASHED_FIELDS = """
                        COALESCE(%(prev)s, ''),
                        %(new)scompany_id::text,
                        COALESCE(%(new)sactor_user_id::text, ''),
                        COALESCE(%(new)sactor_role::text, ''),
                        %(new)saction,
                        %(new)sentity_type,
                        COALESCE(%(new)sentity_id::text, ''),
                        COALESCE(%(new)spage_id::text, ''),
                        COALESCE(%(new)sold_data::text, ''),
                        COALESCE(%(new)snew_data::text, ''),
                        COALESCE(%(new)sdiff::text, ''),
                        %(new)ssource,
                        COALESCE(%(new)sai_session_id::text, ''),
                        COALESCE(%(new)sip_address::text, ''),
                        COALESCE(%(new)suser_agent, ''),
                        %(new)screated_at::text
"""

_OLD_HASHED_FIELDS = """
                        COALESCE(%(prev)s, ''),
                        %(new)scompany_id::text,
                        COALESCE(%(new)sactor_user_id::text, ''),
                        %(new)saction,
                        %(new)sentity_type,
                        COALESCE(%(new)sentity_id::text, ''),
                        COALESCE(%(new)sold_data::text, ''),
                        COALESCE(%(new)snew_data::text, ''),
                        %(new)ssource,
                        %(new)screated_at::text
"""


def _trigger_sql(fields: str) -> str:
    body = fields % {"prev": "v_prev_hash", "new": "NEW."}
    return f"""
        CREATE OR REPLACE FUNCTION fn_audit_logs_hash_chain() RETURNS trigger AS $$
        DECLARE
            v_prev_hash TEXT;
        BEGIN
            -- Serialises audit inserts for the rest of this transaction.
            -- `SELECT ... FOR UPDATE` on the tail row does not: under READ
            -- COMMITTED two transactions can both end up reading the same
            -- previous row and fork the chain.
            PERFORM pg_advisory_xact_lock({_CHAIN_LOCK_KEY});

            SELECT row_hash INTO v_prev_hash
            FROM audit_logs
            ORDER BY id DESC
            LIMIT 1;

            NEW.created_at := COALESCE(NEW.created_at, now());
            NEW.prev_hash := v_prev_hash;
            NEW.row_hash := encode(
                digest(
                    concat_ws('|',{body}
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


def _rehash_sql(fields: str) -> str:
    """Recompute every existing row's hash in `id` order, threading each
    row's new hash into the next row's `prev_hash`."""
    body = fields % {"prev": "v_prev", "new": "r."}
    return f"""
        DO $$
        DECLARE
            r RECORD;
            v_prev TEXT := NULL;
            v_hash TEXT;
        BEGIN
            FOR r IN SELECT * FROM audit_logs ORDER BY id LOOP
                v_hash := encode(
                    digest(
                        concat_ws('|',{body}
                        ),
                        'sha256'
                    ),
                    'hex'
                );
                UPDATE audit_logs
                SET prev_hash = v_prev, row_hash = v_hash
                WHERE id = r.id;
                v_prev := v_hash;
            END LOOP;
        END $$;
    """


def upgrade() -> None:
    op.execute(_trigger_sql(_HASHED_FIELDS))
    op.execute(_rehash_sql(_HASHED_FIELDS))


def downgrade() -> None:
    op.execute(_trigger_sql(_OLD_HASHED_FIELDS))
    op.execute(_rehash_sql(_OLD_HASHED_FIELDS))
