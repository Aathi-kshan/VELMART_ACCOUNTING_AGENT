"""Drop dashboard_widgets — a feature nothing could ever populate

Revision ID: 0022
Revises: 0021

`dashboard_widgets` had a model, a 200-line service, four routes, two audit
actions, a Flutter repository and a test file. It had **no INSERT anywhere in
the application**: there was no create endpoint and no other code path that
made a row. `docs/API.md` said as much in passing — "nothing in the app
creates a new one" — so in production the table could only ever be empty, and
every one of those endpoints could only ever return nothing.

The tests hid it by seeding rows with raw SQL, commented in that file as "the
only way to get a widget".

Removed rather than completed, on the product owner's decision: shipping the
missing creation path would have meant designing and securing a feature
nobody had asked to finish, where deleting it removes roughly 400 lines and
four endpoints' worth of surface that still had to be permission-checked,
audited and maintained.

Kept: `GET /reconciliation` and `GET /dashboard/digest`, which are unrelated
to widgets and genuinely used.

The downgrade recreates the table with its RLS policy and grants, so the
schema can be restored — but the rows cannot, and there were none to lose.
"""

from __future__ import annotations

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dashboard_widgets CASCADE;")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE dashboard_widgets (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            page_id     UUID REFERENCES pages(id) ON DELETE CASCADE,
            title       TEXT NOT NULL,
            widget_type TEXT NOT NULL,
            config      JSONB NOT NULL DEFAULT '{}'::jsonb,
            position    INTEGER NOT NULL DEFAULT 0,
            visible_to  TEXT NOT NULL DEFAULT 'BOTH',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("ALTER TABLE dashboard_widgets ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON dashboard_widgets
          USING (company_id = current_setting('app.company_id', true)::uuid);
        """
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON dashboard_widgets TO app_user;"
    )
