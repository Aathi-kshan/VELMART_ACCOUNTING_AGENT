"""page engine: pages, page_columns, page_validations, page_access, records

Revision ID: 0002
Revises: 0001
Create Date: plan section 8.3
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE page_kind AS ENUM ('REGISTER', 'LEDGER');")

    op.execute(
        """
        CREATE TYPE column_type AS ENUM (
          'TEXT','LONG_TEXT','NUMBER','CURRENCY','PERCENT','DATE','DATETIME',
          'BOOLEAN','SELECT','MULTI_SELECT','RECORD_REF','STORE_REF','USER_REF',
          'FORMULA','ATTACHMENT'
        );
        """
    )

    op.execute("CREATE TYPE record_status AS ENUM ('ACTIVE','REVERSED','VOID');")

    op.execute(
        """
        CREATE TABLE pages (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id     UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            key            TEXT NOT NULL,
            name           TEXT NOT NULL,
            description    TEXT,
            icon           TEXT,
            kind           page_kind NOT NULL DEFAULT 'REGISTER',
            date_column_key TEXT,
            store_column_key TEXT,
            projection_map JSONB NOT NULL DEFAULT '{}'::jsonb,
            is_archived    BOOLEAN NOT NULL DEFAULT FALSE,
            created_by     UUID NOT NULL REFERENCES users(id),
            version        INTEGER NOT NULL DEFAULT 1,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (company_id, key)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE page_columns (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            page_id      UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            key          TEXT NOT NULL,
            name         TEXT NOT NULL,
            data_type    column_type NOT NULL,
            position     INTEGER NOT NULL,
            is_required  BOOLEAN NOT NULL DEFAULT FALSE,
            is_indexed   BOOLEAN NOT NULL DEFAULT FALSE,
            is_protected BOOLEAN NOT NULL DEFAULT FALSE,
            config       JSONB NOT NULL DEFAULT '{}'::jsonb,
            description  TEXT,
            is_archived  BOOLEAN NOT NULL DEFAULT FALSE,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (page_id, key)
        );
        """
    )

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
        CREATE TABLE page_access (
            page_id    UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            can_view   BOOLEAN NOT NULL DEFAULT TRUE,
            can_create BOOLEAN NOT NULL DEFAULT TRUE,
            PRIMARY KEY (page_id, user_id)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE records (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            page_id         UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            store_id        UUID REFERENCES stores(id),
            occurred_at     TIMESTAMPTZ NOT NULL,
            business_date   DATE NOT NULL,
            data            JSONB NOT NULL DEFAULT '{}'::jsonb,
            status          record_status NOT NULL DEFAULT 'ACTIVE',
            reverses_id     UUID REFERENCES records(id),
            needs_review    BOOLEAN NOT NULL DEFAULT FALSE,
            created_by      UUID NOT NULL REFERENCES users(id),
            updated_by      UUID REFERENCES users(id),
            source          TEXT NOT NULL DEFAULT 'APP',
            client_uuid     UUID,
            import_batch_id UUID,
            version         INTEGER NOT NULL DEFAULT 1,
            is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_reason  TEXT,
            num_1 NUMERIC(14,2), num_2 NUMERIC(14,2), num_3 NUMERIC(14,2), num_4 NUMERIC(14,2),
            date_1 DATE, date_2 DATE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    op.execute(
        """
        CREATE INDEX ix_records_page_time  ON records (page_id, business_date DESC, occurred_at DESC)
               WHERE is_deleted = FALSE;
        """
    )
    op.execute("CREATE INDEX ix_records_data_gin   ON records USING GIN (data jsonb_path_ops);")
    op.execute(
        "CREATE INDEX ix_records_num1       ON records (page_id, num_1) WHERE is_deleted = FALSE;"
    )
    op.execute(
        "CREATE INDEX ix_records_date1      ON records (page_id, date_1) WHERE is_deleted = FALSE;"
    )
    op.execute("CREATE INDEX ix_records_store      ON records (store_id, business_date DESC);")
    op.execute(
        """
        CREATE UNIQUE INDEX ux_records_client_uuid ON records (company_id, client_uuid)
               WHERE client_uuid IS NOT NULL;
        """
    )

    # full-text-ish search across whatever the Owner stored
    op.execute(
        """
        CREATE INDEX ix_records_search ON records
               USING GIN ((data::text) gin_trgm_ops);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS records;")
    op.execute("DROP TABLE IF EXISTS page_access;")
    op.execute("DROP TABLE IF EXISTS page_validations;")
    op.execute("DROP TABLE IF EXISTS page_columns;")
    op.execute("DROP TABLE IF EXISTS pages;")
    op.execute("DROP TYPE IF EXISTS record_status;")
    op.execute("DROP TYPE IF EXISTS column_type;")
    op.execute("DROP TYPE IF EXISTS page_kind;")
