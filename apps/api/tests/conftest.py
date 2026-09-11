"""Test fixtures — a real PostgreSQL, never a mock.

Plan section 24.1 runs integration tests against testcontainers Postgres, and
Phase 0 demonstrated why that matters: the RLS policies, the audit hash-chain
trigger, the generated columns and the role grants are all database behaviour
that a mocked session would happily pretend to have.

The container is built once per session, migrated to head, and each test runs
against a schema truncated back to empty.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

API_ROOT = Path(__file__).resolve().parents[1]

#: Tables that migrations populate and tests must not wipe.
_PRESERVE = {"alembic_version"}


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A PostgreSQL 18 container, migrated to head."""
    with PostgresContainer(
        "postgres:18", username="velmart", password="velmart", dbname="velmart"
    ) as container:
        sync_url = container.get_connection_url()  # postgresql+psycopg2://...
        plain = sync_url.replace("postgresql+psycopg2://", "postgresql://")

        env = {**os.environ, "DATABASE_URL": plain}
        subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["uv", "run", "alembic", "upgrade", "head"],  # noqa: S607
            cwd=API_ROOT,
            env=env,
            check=True,
            capture_output=True,
        )
        yield plain


@pytest.fixture(scope="session", autouse=True)
def _settings(postgres_url: str) -> Iterator[None]:
    """Point the app at the container before anything imports settings."""
    os.environ["DATABASE_URL"] = postgres_url
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-" + "x" * 60)  # >= 64 bytes
    os.environ.setdefault("ENVIRONMENT", "development")

    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def engine(postgres_url: str) -> AsyncIterator[object]:
    from app.config import to_asyncpg_url

    eng = create_async_engine(to_asyncpg_url(postgres_url), poolclass=None)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:  # noqa: ANN001
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s


@pytest.fixture(autouse=True)
async def _clean_tables(engine) -> AsyncIterator[None]:  # noqa: ANN001
    """Empty every table between tests.

    `audit_logs` has UPDATE/DELETE revoked from app_user, but tests connect as
    the container's owner role, which bypasses that — deliberately, so the
    append-only guarantee stays testable rather than being worked around.
    """
    yield
    from sqlalchemy import text

    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        tables = [t for (t,) in result.all() if t not in _PRESERVE]
        if tables:
            await conn.execute(
                text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")
            )


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An HTTP client wired to the app in-process."""
    from app.db.session import get_engine, get_sessionmaker
    from app.main import create_app

    get_engine.cache_clear()
    get_sessionmaker.cache_clear()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --------------------------------------------------------------------------
# Factories
# --------------------------------------------------------------------------


@pytest.fixture
async def company(session: AsyncSession) -> uuid.UUID:
    from sqlalchemy import text

    company_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO companies (id, name) VALUES (:id, 'Test Supermarket')"),
        {"id": str(company_id)},
    )
    await session.commit()
    return company_id


@pytest.fixture
def owner_password() -> str:
    return "correct-horse-battery"


@pytest.fixture
async def owner(session: AsyncSession, company: uuid.UUID, owner_password: str) -> uuid.UUID:
    from sqlalchemy import text

    from app.core.security import hash_password

    user_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO users (id, company_id, email, full_name, password_hash, role)
            VALUES (:id, :company_id, :email, 'Test Owner', :pw, 'OWNER')
            """
        ),
        {
            "id": str(user_id),
            "company_id": str(company),
            "email": "owner@test.lk",
            "pw": hash_password(owner_password),
        },
    )
    await session.commit()
    return user_id
