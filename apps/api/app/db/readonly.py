"""The read-only engine used by the AI read path (ai_reader role).

Kept deliberately separate from `session.py` so no AI code can reach the
read-write engine by accident. `ai_reader` has SELECT only, cannot see `users`,
`refresh_tokens` or `idempotency_keys`, and carries an 8-second statement
timeout (plan sections 8.8 and 16.5).

Unused until P7; the separation exists from the start.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


class ReadOnlyEngineUnavailableError(RuntimeError):
    """Raised when the AI read path is used without DATABASE_URL_READONLY set."""


@lru_cache
def get_readonly_engine() -> AsyncEngine:
    settings = get_settings()
    url = settings.database_url_readonly
    if not url:
        raise ReadOnlyEngineUnavailableError(
            "DATABASE_URL_READONLY is not configured; the AI read path requires the "
            "ai_reader role and must never fall back to the read-write engine."
        )
    return create_async_engine(
        url,
        pool_size=2,
        max_overflow=2,
        pool_pre_ping=True,
        echo=False,
        connect_args={
            "server_settings": {"statement_timeout": str(settings.AI_DB_STATEMENT_TIMEOUT_MS)}
        },
    )


@lru_cache
def get_readonly_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_readonly_engine(), expire_on_commit=False, autoflush=False)


async def get_readonly_session() -> AsyncIterator[AsyncSession]:
    async with get_readonly_sessionmaker()() as session:
        yield session


async def dispose_readonly_engine() -> None:
    if get_readonly_engine.cache_info().currsize:
        await get_readonly_engine().dispose()
