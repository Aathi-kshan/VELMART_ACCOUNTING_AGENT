"""The cross-tenant engine used by the nightly ops jobs (`migrator` role).

Kept deliberately separate from `session.py`/`readonly.py` — `migrator` has
`BYPASSRLS` (migration 0012), so no request path may ever reach this engine
by accident. It exists for exactly one reason: the audit hash chain is one
global sequence across every company (no `WHERE company_id` in the trigger
itself, migration 0005), so verifying it needs a connection that sees every
tenant's rows in one true insertion-order pass, not the company-scoped view
`app_user`/`ai_reader` are restricted to.

Used only by `app/tasks/*.py`, invoked via `python -m app.tasks.nightly` —
never imported by `app/routers/`, `app/services/`, or `app/main.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


class MigratorEngineUnavailableError(RuntimeError):
    """Raised when a nightly job runs without DATABASE_URL_MIGRATOR set."""


@lru_cache
def get_migrator_engine() -> AsyncEngine:
    settings = get_settings()
    url = settings.database_url_migrator
    if not url:
        raise MigratorEngineUnavailableError(
            "DATABASE_URL_MIGRATOR is not configured; the nightly ops jobs require the "
            "migrator (BYPASSRLS) role and must never fall back to the read-write engine."
        )
    return create_async_engine(url, pool_size=2, max_overflow=2, pool_pre_ping=True, echo=False)


@lru_cache
def get_migrator_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_migrator_engine(), expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def get_migrator_session() -> AsyncIterator[AsyncSession]:
    async with get_migrator_sessionmaker()() as session:
        yield session


async def dispose_migrator_engine() -> None:
    if get_migrator_engine.cache_info().currsize:
        await get_migrator_engine().dispose()
