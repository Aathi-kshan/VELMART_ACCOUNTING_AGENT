"""remove CSV import and validation rules — full feature removal

Revision ID: 0014
Revises: 0013
Create Date: CSV import and page_validations removed (product decision)

Both features were removed completely, not just their UI/API surface.
`import_batches` and `page_validations` are used only by these two features
(confirmed via a full-repo reference search before writing this migration)
— safe to drop outright. `import_batch_id` on `records` and all six native
business tables was populated only by the now-deleted CSV import commit
path; dropped here too rather than left as permanently-`NULL` dead weight.

CSV *export* and validation of ordinary column data (required/type/options)
are unrelated, unaffected features and keep their own tables/columns as-is.
"""

from __future__ import annotations

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_BUSINESS_TABLES = (
    "employee_salaries",
    "purchases",
    "expenses",
    "daily_revenue",
    "cash_ledger",
    "cheques",
)


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS import_batches;")
    op.execute("DROP TABLE IF EXISTS page_validations;")
    op.execute("ALTER TABLE records DROP COLUMN IF EXISTS import_batch_id;")
    for table in _BUSINESS_TABLES:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS import_batch_id;")


def downgrade() -> None:
    # Dev-rollback only: recreates the columns/tables this migration drops,
    # but not the RLS policy / role grants migrations 0006/0008/0009 applied
    # to them — reapply those manually if this downgrade is ever actually
    # exercised against a real environment.
    op.execute("ALTER TABLE records ADD COLUMN import_batch_id UUID;")
    for table in _BUSINESS_TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN import_batch_id UUID;")

    op.execute(
        """
        CREATE TABLE page_validations (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            page_id     UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            expression  TEXT NOT NULL,
            severity    TEXT NOT NULL DEFAULT 'ERROR',
            message     TEXT NOT NULL,
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE import_batches (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id    UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            page_id       UUID NOT NULL REFERENCES pages(id),
            file_name     TEXT NOT NULL,
            mapping       JSONB NOT NULL,
            total_rows    INTEGER NOT NULL,
            imported_rows INTEGER NOT NULL DEFAULT 0,
            skipped_rows  INTEGER NOT NULL DEFAULT 0,
            status        TEXT NOT NULL DEFAULT 'PENDING',
            error_report  JSONB,
            created_by    UUID NOT NULL REFERENCES users(id),
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
