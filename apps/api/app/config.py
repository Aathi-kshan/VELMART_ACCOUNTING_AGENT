"""Application settings, validated at boot (plan section 23.5).

A missing secret crashes the container immediately rather than surfacing as a 500
three hours later. Production requires every external credential; development
leaves the AI, Sentry and bucket settings optional so local work is not blocked
until those phases arrive.
"""

from __future__ import annotations

import enum
from decimal import Decimal
from functools import lru_cache
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(enum.StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


def to_asyncpg_url(url: str) -> str:
    """Normalise a Postgres URL onto the asyncpg driver.

    Railway and most providers hand out `postgres://` or `postgresql://`;
    SQLAlchemy's async engine needs the driver spelled out. This is the single
    implementation of that rule — `alembic/env.py` imports it too.
    """
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    LOG_LEVEL: str = "INFO"

    # --- database ---------------------------------------------------------
    DATABASE_URL: str
    DATABASE_URL_READONLY: str | None = None  # ai_reader role; required in production
    #: `migrator` role — schema owner, so RLS-exempt by default (P5 §12:
    #: `ALTER ROLE migrator BYPASSRLS`, migration 0012). Used only by
    #: `app/tasks/*.py` (the nightly cron), never a request path: the audit
    #: chain is one global sequence across every tenant (no `WHERE
    #: company_id` in the hash-chain trigger itself), so verifying it needs
    #: a connection RLS doesn't scope to one company at a time.
    DATABASE_URL_MIGRATOR: str | None = None
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_STATEMENT_TIMEOUT_MS: int = 15_000
    #: The AI read path gets a tighter ceiling than the app (plan section 16.5).
    AI_DB_STATEMENT_TIMEOUT_MS: int = 8_000

    # --- object storage ---------------------------------------------------
    AWS_ENDPOINT_URL: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_S3_BUCKET_NAME: str | None = None

    # --- auth -------------------------------------------------------------
    JWT_SECRET_KEY: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS512"
    ACCESS_TOKEN_MINUTES: int = 15
    REFRESH_TOKEN_DAYS: int = 30

    # --- AI ---------------------------------------------------------------
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    AI_MODEL_ROUTER: str | None = None
    AI_MODEL_DEFAULT: str | None = None
    AI_MODEL_ANALYSIS: str | None = None
    AI_MAX_TOOL_CALLS: int = 8
    AI_TIMEOUT_SECONDS: int = 12
    AI_DAILY_USD_CAP_DEFAULT: Decimal = Decimal("3.00")

    # --- observability and limits ----------------------------------------
    SENTRY_DSN: str | None = None
    MAX_UPLOAD_MB: int = 10
    MAX_CSV_MB: int = 10
    MAX_PAGES_PER_COMPANY: int = 100
    MAX_COLUMNS_PER_PAGE: int = 60
    RATE_LIMIT_PER_MINUTE: int = 100
    #: How many reverse proxies sit in front of this app. 0 (the default)
    #: means `X-Forwarded-For` is ignored entirely — the header is
    #: client-supplied, so trusting it without a proxy in front lets a caller
    #: forge a new IP per request and evade IP rate limiting completely.
    #: Set to 1 behind a single terminating proxy such as Railway, or the
    #: whole deployment shares one login-attempt bucket.
    TRUSTED_PROXY_HOPS: int = 0
    #: Where the nightly `pg_dump` writes. Unset means a temp directory,
    #: which on a container platform is discarded on the next redeploy — the
    #: dump succeeds and then vanishes. Production must point this at a
    #: mounted volume; `app/tasks/export_build.py` warns loudly when it is
    #: unset so a backup that will not survive is not mistaken for one that
    #: will.
    BACKUP_DIR: str | None = None

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT is Environment.PRODUCTION

    @property
    def database_url(self) -> str:
        return to_asyncpg_url(self.DATABASE_URL)

    @property
    def database_url_readonly(self) -> str | None:
        return to_asyncpg_url(self.DATABASE_URL_READONLY) if self.DATABASE_URL_READONLY else None

    @property
    def database_url_migrator(self) -> str | None:
        return to_asyncpg_url(self.DATABASE_URL_MIGRATOR) if self.DATABASE_URL_MIGRATOR else None

    @model_validator(mode="after")
    def _require_production_secrets(self) -> Self:
        """In production every external credential must be present at boot."""
        if not self.is_production:
            return self

        required = {
            "DATABASE_URL_READONLY": self.DATABASE_URL_READONLY,
            "DATABASE_URL_MIGRATOR": self.DATABASE_URL_MIGRATOR,
            "AWS_ENDPOINT_URL": self.AWS_ENDPOINT_URL,
            "AWS_ACCESS_KEY_ID": self.AWS_ACCESS_KEY_ID,
            "AWS_SECRET_ACCESS_KEY": self.AWS_SECRET_ACCESS_KEY,
            "AWS_S3_BUCKET_NAME": self.AWS_S3_BUCKET_NAME,
            "OPENROUTER_API_KEY": self.OPENROUTER_API_KEY,
            "AI_MODEL_ROUTER": self.AI_MODEL_ROUTER,
            "AI_MODEL_DEFAULT": self.AI_MODEL_DEFAULT,
            "AI_MODEL_ANALYSIS": self.AI_MODEL_ANALYSIS,
            "SENTRY_DSN": self.SENTRY_DSN,
        }
        missing = sorted(name for name, value in required.items() if not value)
        if missing:
            raise ValueError(
                "ENVIRONMENT=production requires these variables: " + ", ".join(missing)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    # Values come from the environment / .env, not from call arguments.
    return Settings()
