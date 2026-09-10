"""dashboard_widgets

Revision ID: 0004
Revises: 0003
Create Date: plan section 8.4
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE dashboard_widgets (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            page_id     UUID REFERENCES pages(id) ON DELETE CASCADE,
            title       TEXT NOT NULL,
            widget_type TEXT NOT NULL,
            config      JSONB NOT NULL,
            position    INTEGER NOT NULL DEFAULT 0,
            visible_to  user_role,
            created_by  UUID NOT NULL REFERENCES users(id),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dashboard_widgets;")
