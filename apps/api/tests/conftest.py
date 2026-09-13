"""Test fixtures — a real PostgreSQL, never a mock.

Plan section 24.1 runs integration tests against testcontainers Postgres, and
Phase 0 demonstrated why that matters: the RLS policies, the audit hash-chain
trigger, the generated columns and the role grants are all database behaviour
that a mocked session would happily pretend to have.

The container is built once per session, migrated to head, and each test runs
against a schema truncated back to empty.

P2 closes a gap found while planning that phase: PostgreSQL does not enforce
Row-Level Security against a table's owner/superuser, so if the running app
itself connected as the container's superuser (as it did through P1), every
RLS policy would be silently bypassed in every test. `DATABASE_URL` — what
`app.db.session.get_engine()` actually connects with — is therefore
`app_user` (migration 0001's least-privilege role, matching production), not
the superuser. Fixtures that set up data ahead of any tenant context
(`company`, `owner`, `_clean_tables`) still use the superuser `engine`/
`session` fixtures below, since bypassing RLS is exactly what test setup and
teardown need.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

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


@pytest.fixture(scope="session")
def app_user_url(postgres_url: str) -> str:
    """The same container and database, but as `app_user` (migration 0001)
    rather than the superuser — what the running app must connect as for RLS
    to mean anything. See the module docstring."""
    parts = urlsplit(postgres_url)
    netloc = f"app_user:CHANGE_ME@{parts.hostname}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


@pytest.fixture(scope="session")
def ai_reader_url(postgres_url: str) -> str:
    """The same container and database, but as `ai_reader` (migration 0001) —
    the role every AI tool call must use (app/dependencies/db.py's
    `get_ai_reader_session`). SELECT-only, cannot see `users`/
    `refresh_tokens`/`idempotency_keys`, and not `BYPASSRLS`."""
    parts = urlsplit(postgres_url)
    netloc = f"ai_reader:CHANGE_ME@{parts.hostname}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


@pytest.fixture(scope="session", autouse=True)
def _settings(app_user_url: str, ai_reader_url: str) -> Iterator[None]:
    """Point the app at the container before anything imports settings.

    `DATABASE_URL` is the `app_user` connection, not the superuser one — see
    the module docstring for why. Migrations (in `postgres_url` above) and
    test data setup (the `engine`/`session` fixtures below) go through the
    superuser connection directly, unaffected by this.
    """
    os.environ["DATABASE_URL"] = app_user_url
    os.environ["DATABASE_URL_READONLY"] = ai_reader_url
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


@pytest.fixture
async def app_user_session(app_user_url: str) -> AsyncIterator[AsyncSession]:
    """A session connected as `app_user` — the same role the running app
    uses — for tests that must exercise real RLS enforcement directly rather
    than through the superuser `session` fixture above, which RLS never
    restricts regardless of context."""
    from app.config import to_asyncpg_url

    eng = create_async_engine(to_asyncpg_url(app_user_url), poolclass=None)
    maker = async_sessionmaker(eng, expire_on_commit=False)
    async with maker() as s:
        yield s
    await eng.dispose()


@pytest.fixture
async def ai_reader_session(ai_reader_url: str) -> AsyncIterator[AsyncSession]:
    """A raw connection as `ai_reader`, with no RLS context armed — for tests
    that check the role's own grants directly (SELECT-only, cannot see
    `users`/`refresh_tokens`/`idempotency_keys`), as opposed to
    `get_ai_reader_session` which additionally arms RLS from a
    `SecurityContext`."""
    from app.config import to_asyncpg_url

    eng = create_async_engine(to_asyncpg_url(ai_reader_url), poolclass=None)
    maker = async_sessionmaker(eng, expire_on_commit=False)
    async with maker() as s:
        yield s
    await eng.dispose()


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


@pytest.fixture
def manager_password() -> str:
    return "correct-horse-battery"


@pytest.fixture
async def manager(session: AsyncSession, company: uuid.UUID, manager_password: str) -> uuid.UUID:
    from sqlalchemy import text

    from app.core.security import hash_password

    user_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO users (id, company_id, email, full_name, password_hash, role)
            VALUES (:id, :company_id, :email, 'Test Manager', :pw, 'MANAGER')
            """
        ),
        {
            "id": str(user_id),
            "company_id": str(company),
            "email": "manager@test.lk",
            "pw": hash_password(manager_password),
        },
    )
    await session.commit()
    return user_id


@pytest.fixture
async def system_pages(session: AsyncSession, company: uuid.UUID, owner: uuid.UUID) -> None:
    """Seeds the six P3.5 system pages (Employee Salary, Purchases, Expenses,
    Daily Revenue, Cash Ledger, Cheques) for `company` — the same
    `register_system_pages` a real deployment's `seed_demo.py` calls. Uses
    the superuser `session` fixture, so no RLS context needs setting."""
    from app.core.context import SecurityContext
    from app.models.user import UserRole
    from app.services.page_service import register_system_pages

    ctx = SecurityContext(user_id=owner, company_id=company, role=UserRole.OWNER, store_ids=())
    await register_system_pages(session, ctx, company)
    await session.commit()


@pytest.fixture
async def system_page_ids(
    session: AsyncSession, company: uuid.UUID, system_pages: None
) -> dict[str, str]:
    """`page.key` -> `page.id` for the six seeded system pages, so tests
    don't each need their own `GET /pages` round trip just to find one."""
    from sqlalchemy import text

    result = await session.execute(
        text("SELECT key, id FROM pages WHERE company_id = :company_id AND is_system = true"),
        {"company_id": str(company)},
    )
    return {key: str(page_id) for key, page_id in result.all()}
