"""attachments, import_batches

Revision ID: 0003
Revises: 0002
Create Date: plan section 8.4
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE attachments (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id   UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            record_id    UUID NOT NULL REFERENCES records(id) ON DELETE CASCADE,
            column_key   TEXT,
            object_key   TEXT NOT NULL UNIQUE,
            file_name    TEXT NOT NULL,
            content_type TEXT NOT NULL,
            size_bytes   BIGINT NOT NULL,
            sha256       TEXT NOT NULL,
            uploaded_by  UUID NOT NULL REFERENCES users(id),
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX ix_attachments_record ON attachments (record_id);")

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


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS import_batches;")
    op.execute("DROP TABLE IF EXISTS attachments;")
