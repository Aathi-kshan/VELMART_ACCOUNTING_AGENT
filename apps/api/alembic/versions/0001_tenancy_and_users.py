"""tenancy and identity: extensions, companies, company_settings, stores, users, refresh_tokens, idempotency_keys

Revision ID: 0001
Revises:
Create Date: plan section 8.2 / 8.8
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')  # gen_random_uuid()
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm";')  # fuzzy search over record text
    op.execute('CREATE EXTENSION IF NOT EXISTS "citext";')

    op.execute(
        """
        CREATE TABLE companies (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name       TEXT NOT NULL,
            currency   CHAR(3) NOT NULL DEFAULT 'LKR',
            timezone   TEXT NOT NULL DEFAULT 'Asia/Colombo',
            is_active  BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    op.execute(
        """
        CREATE TABLE company_settings (
            company_id       UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            day_cutoff_hour  SMALLINT NOT NULL DEFAULT 2,
            ai_enabled       BOOLEAN NOT NULL DEFAULT TRUE,
            ai_daily_usd_cap NUMERIC(8,2) NOT NULL DEFAULT 3.00,
            ai_model_config  JSONB NOT NULL DEFAULT '{}'::jsonb,
            ai_allow_delete_proposals BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    op.execute(
        """
        CREATE TABLE stores (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            code       TEXT NOT NULL,
            name       TEXT NOT NULL,
            address    TEXT,
            is_active  BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (company_id, code)
        );
        """
    )

    op.execute("CREATE TYPE user_role AS ENUM ('OWNER', 'MANAGER');")  # exactly two

    op.execute(
        """
        CREATE TABLE users (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            email           CITEXT NOT NULL,
            full_name       TEXT NOT NULL,
            phone           TEXT,
            password_hash   TEXT NOT NULL,
            role            user_role NOT NULL,
            token_version   INTEGER NOT NULL DEFAULT 1,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            last_login_at   TIMESTAMPTZ,
            failed_attempts SMALLINT NOT NULL DEFAULT 0,
            locked_until    TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (company_id, email)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE user_stores (
            user_id  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            store_id UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
            PRIMARY KEY (user_id, store_id)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE refresh_tokens (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash  TEXT NOT NULL UNIQUE,
            device_id   TEXT NOT NULL,
            device_name TEXT,
            expires_at  TIMESTAMPTZ NOT NULL,
            revoked_at  TIMESTAMPTZ,
            replaced_by UUID REFERENCES refresh_tokens(id),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    # idempotency without Redis; the nightly job deletes rows older than 48h
    op.execute(
        """
        CREATE TABLE idempotency_keys (
            key           TEXT PRIMARY KEY,
            user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            endpoint      TEXT NOT NULL,
            request_hash  TEXT NOT NULL,
            response_body JSONB,
            status_code   INTEGER,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    # database roles (plan section 8.8) — created here so later migrations can
    # GRANT/REVOKE against them; passwords are placeholders, rotate post-deploy.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
                CREATE ROLE app_user LOGIN PASSWORD 'CHANGE_ME';
            END IF;
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_reader') THEN
                CREATE ROLE ai_reader LOGIN PASSWORD 'CHANGE_ME';
            END IF;
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'migrator') THEN
                CREATE ROLE migrator LOGIN PASSWORD 'CHANGE_ME';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS idempotency_keys;")
    op.execute("DROP TABLE IF EXISTS refresh_tokens;")
    op.execute("DROP TABLE IF EXISTS user_stores;")
    op.execute("DROP TABLE IF EXISTS users;")
    op.execute("DROP TYPE IF EXISTS user_role;")
    op.execute("DROP TABLE IF EXISTS stores;")
    op.execute("DROP TABLE IF EXISTS company_settings;")
    op.execute("DROP TABLE IF EXISTS companies;")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
                DROP ROLE app_user;
            END IF;
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_reader') THEN
                DROP ROLE ai_reader;
            END IF;
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'migrator') THEN
                DROP ROLE migrator;
            END IF;
        END
        $$;
        """
    )
