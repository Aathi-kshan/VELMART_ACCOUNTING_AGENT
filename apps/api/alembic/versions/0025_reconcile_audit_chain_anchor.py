"""Reconcile audit_chain_anchor after chain_seq changed what last_id means

Revision ID: 0025
Revises: 0024

Found while seeding realistic volume for the restore-drill RTO measurement
(the actual point of this session's work) — the audit chain reported
`truncation_detected=True` on a database nothing had truncated. Traced it
back to a migration-sequencing bug, not a false alarm in the verifier logic
itself.

Migration `0019` created `audit_chain_anchor` when `last_id` meant
`audit_logs.id` — the newest row's `BIGSERIAL` primary key, the only
ordering that existed at the time. Migration `0021` introduced `chain_seq`
(allocated inside the chain lock, because `id` is assigned by Postgres
*before* the trigger runs and so is not safe to order the chain by under
concurrency — see that migration's own docstring) and updated
`app/tasks/audit_chain_verify.py`'s Python code to read and write `last_id`
as a `chain_seq` value everywhere. **No migration converted an existing
anchor row from the old meaning to the new one.**

Concretely: any deployment that ran the nightly verifier even once between
0019 and 0021 landing wrote an anchor whose `last_id` is an `audit_logs.id`.
After upgrading to 0021+, `_check_anchor` reads that same number as a
`chain_seq` — a different row, almost certainly with a different hash — and
reports it as tampering. This development database hit exactly that path.

This is a one-time reconciliation, not a design change: recompute the
anchor from the current chain head, exactly what `verify_chain`'s own
`_record_anchor` would write on the next clean run — bringing forward a
stale anchor rather than pretending the gap never existed. It is not a
security-weakening "just believe the current state": no code path resets an
anchor on a chain that is *actually* broken (`_check_anchor`'s comparison
against the stored hash still fires for real tampering), and this only
touches a row already known, by the argument above, to have been computed
under semantics that no longer apply.

Only runs when an anchor row already exists. A missing anchor is already
handled correctly by `_check_anchor` returning "not truncated" on a first
run — nothing to reconcile there.
"""

from __future__ import annotations

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE audit_chain_anchor
        SET last_id = sub.last_seq,
            last_row_hash = sub.last_row_hash,
            row_count = sub.row_count,
            verified_at = now()
        FROM (
            SELECT
                (SELECT chain_seq FROM audit_logs ORDER BY chain_seq DESC LIMIT 1) AS last_seq,
                (SELECT row_hash  FROM audit_logs ORDER BY chain_seq DESC LIMIT 1) AS last_row_hash,
                (SELECT count(*)  FROM audit_logs) AS row_count
        ) AS sub
        WHERE audit_chain_anchor.only_row
          AND EXISTS (SELECT 1 FROM audit_logs);
        """
    )


def downgrade() -> None:
    # There is no reliable way back to the pre-0021 (id-based) anchor value —
    # that information was already lost the moment 0021 shipped without this
    # reconciliation. A no-op is honest about that rather than writing back a
    # value that would just be wrong in the other direction.
    pass
