"""Rename the "Purchases" system page's display name to "Purchases for Cash"

Revision ID: 0016
Revises: 0015

`register_system_pages` (app/services/page_service.py) seeds the six system
pages per company, but seeding is idempotent per `key` — a company that
already has a `purchases` page keeps its existing `name` forever, since the
seeding code skips any key that already exists (page_service.py's own
`existing.add(...)` check). Editing `_SYSTEM_PAGES["purchases"]["name"]`
in code therefore only affects companies seeded *after* this migration
lands; every already-seeded company (including this dev environment's own
"Velmart Demo Supermarket") needs its existing row updated directly.

Only `name` (the user-facing display label) changes here. `key`,
`storage_table`, and the physical `purchases` table are untouched — they
are internal identifiers, not display text, and nothing about the schema,
the six `SYSTEM_PAGE_KEYS`/`RESERVED_PAGE_KEYS`, or `STORAGE_MODELS`
depends on `name`.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

OLD_NAME = "Purchases"
NEW_NAME = "Purchases for Cash"


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE pages SET name = :new_name "
            "WHERE key = 'purchases' AND is_system IS TRUE AND name = :old_name"
        ).bindparams(new_name=NEW_NAME, old_name=OLD_NAME)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE pages SET name = :old_name "
            "WHERE key = 'purchases' AND is_system IS TRUE AND name = :new_name"
        ).bindparams(new_name=NEW_NAME, old_name=OLD_NAME)
    )
