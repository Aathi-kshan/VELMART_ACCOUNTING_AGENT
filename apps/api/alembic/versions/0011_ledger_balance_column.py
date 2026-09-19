"""pages.balance_column_key — ledger running-balance support

Revision ID: 0011
Revises: 0010
Create Date: plan section 11.5 / P4 §8

`GET /pages/{id}/running-balance` (P4 §8) computes a cumulative sum over one
NUMBER/CURRENCY column, in the page's default row order — this is the column
it sums, named the same way `date_column_key`/`store_column_key` already
name a column by key rather than duplicating its value anywhere. Nullable:
only `kind = LEDGER` pages are expected to set it, and nothing else reads it.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pages", sa.Column("balance_column_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("pages", "balance_column_key")
