"""ai_proposal_items.record_id — drop the records(id) FK

Revision ID: 0015
Revises: 0014
Create Date: P8 Lite — a proposal item's record_id must be able to target
either the generic `records` table or a native/system table's own row
(cheques, expenses, purchases, ...), exactly like `RecordHandle`/`get_row`
(app/repositories/records.py) already abstract over both. Migration 0007
gave `record_id` a single FK to `records(id)`, which made a proposal
targeting any system page (e.g. propose_status_change on
`cheques.cheque_status`, the primary real-world use of that tool) fail
outright with a foreign-key violation — there is no single physical table
every business record lives in, so no single-table FK can ever be correct
here. Referential integrity for `record_id` is enforced in application code
instead (`app/ai/tools/propose_tools.py` verifies the row exists via
`get_row` before ever creating a proposal item), the same way `page_id`
already has no cross-check against which storage backend it names.
"""

from __future__ import annotations

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ai_proposal_items DROP CONSTRAINT IF EXISTS ai_proposal_items_record_id_fkey;"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE ai_proposal_items "
        "ADD CONSTRAINT ai_proposal_items_record_id_fkey "
        "FOREIGN KEY (record_id) REFERENCES records(id);"
    )
