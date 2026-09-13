"""Slice 1 — the AI layer's read-only, tenant-scoped database session.

`ai_reader` (migration 0001/0007/0008) is SELECT-only, cannot see `users`/
`refresh_tokens`/`idempotency_keys`, and carries an 8-second statement
timeout. It is **not** `BYPASSRLS` — only `migrator` is — so
`get_ai_reader_session` (app/dependencies/db.py) must still arm RLS from the
caller's `SecurityContext` per transaction, exactly like `get_rls_session`
does for `app_user`. These tests prove all of that against a real Postgres,
not a mock.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.security import hash_password
from app.db.readonly import dispose_readonly_engine, get_readonly_engine, get_readonly_sessionmaker
from app.dependencies.db import get_ai_reader_session
from app.models.user import UserRole


@pytest.fixture(autouse=True)
async def _reset_readonly_engine():
    """`get_readonly_engine`/`get_readonly_sessionmaker` are process-lifetime
    `lru_cache`s, but each test function runs in its own asyncio event loop —
    reusing a pooled asyncpg connection across loops raises "attached to a
    different loop". Dispose and clear after every test so the next one that
    touches the readonly engine builds a fresh one bound to its own loop."""
    yield
    await dispose_readonly_engine()
    get_readonly_engine.cache_clear()
    get_readonly_sessionmaker.cache_clear()


async def _insert_company(session: AsyncSession, name: str) -> uuid.UUID:
    company_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO companies (id, name) VALUES (:id, :name)"),
        {"id": str(company_id), "name": name},
    )
    return company_id


async def _insert_owner(session: AsyncSession, company_id: uuid.UUID, email: str) -> uuid.UUID:
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
            "company_id": str(company_id),
            "email": email,
            "pw": hash_password("correct-horse-battery"),
        },
    )
    return user_id


async def _insert_page(
    session: AsyncSession, company_id: uuid.UUID, created_by: uuid.UUID, key: str
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO pages (id, company_id, key, name, created_by)
            VALUES (:id, :company_id, :key, :key, :created_by)
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "company_id": str(company_id),
            "key": key,
            "created_by": str(created_by),
        },
    )


class TestAiReaderIsReadOnly:
    async def test_insert_is_rejected(self, ai_reader_session: AsyncSession) -> None:
        with pytest.raises(DBAPIError, match="permission denied"):
            await ai_reader_session.execute(
                text("INSERT INTO companies (id, name) VALUES (gen_random_uuid(), 'x')")
            )

    async def test_update_is_rejected(self, ai_reader_session: AsyncSession) -> None:
        with pytest.raises(DBAPIError, match="permission denied"):
            await ai_reader_session.execute(text("UPDATE companies SET name = 'x'"))

    async def test_delete_is_rejected(self, ai_reader_session: AsyncSession) -> None:
        with pytest.raises(DBAPIError, match="permission denied"):
            await ai_reader_session.execute(text("DELETE FROM companies"))


class TestAiReaderExcludedTables:
    @pytest.mark.parametrize("excluded_table", ["users", "refresh_tokens", "idempotency_keys"])
    async def test_select_on_excluded_table_is_rejected(
        self, ai_reader_session: AsyncSession, excluded_table: str
    ) -> None:
        with pytest.raises(DBAPIError, match="permission denied"):
            await ai_reader_session.execute(text(f"SELECT * FROM {excluded_table}"))  # noqa: S608


class TestAiReaderStatementTimeout:
    async def test_slow_query_is_cut_off(self, ai_reader_session: AsyncSession) -> None:
        with pytest.raises(DBAPIError, match="statement timeout"):
            await ai_reader_session.execute(text("SELECT pg_sleep(9)"))


class TestGetAiReaderSessionTenantIsolation:
    async def test_arms_rls_and_scopes_to_caller_company(self, session: AsyncSession) -> None:
        company_a = await _insert_company(session, "Company A")
        company_b = await _insert_company(session, "Company B")
        owner_a = await _insert_owner(session, company_a, "owner-a@test.lk")
        owner_b = await _insert_owner(session, company_b, "owner-b@test.lk")
        await _insert_page(session, company_a, owner_a, "page_a")
        await _insert_page(session, company_b, owner_b, "page_b")
        await session.commit()

        ctx_a = SecurityContext(
            user_id=owner_a, company_id=company_a, role=UserRole.OWNER, store_ids=()
        )
        async with get_readonly_sessionmaker()() as raw:
            async for scoped in get_ai_reader_session(ctx=ctx_a, session=raw):
                rows = (await scoped.execute(text("SELECT key FROM pages"))).scalars().all()
                assert rows == ["page_a"]

        ctx_b = SecurityContext(
            user_id=owner_b, company_id=company_b, role=UserRole.OWNER, store_ids=()
        )
        async with get_readonly_sessionmaker()() as raw:
            async for scoped in get_ai_reader_session(ctx=ctx_b, session=raw):
                rows = (await scoped.execute(text("SELECT key FROM pages"))).scalars().all()
                assert rows == ["page_b"]

    async def test_read_only_still_holds_through_the_dependency(
        self, session: AsyncSession
    ) -> None:
        company = await _insert_company(session, "Company C")
        owner = await _insert_owner(session, company, "owner-c@test.lk")
        await session.commit()

        ctx = SecurityContext(user_id=owner, company_id=company, role=UserRole.OWNER, store_ids=())
        async with get_readonly_sessionmaker()() as raw:
            async for scoped in get_ai_reader_session(ctx=ctx, session=raw):
                with pytest.raises(DBAPIError, match="permission denied"):
                    await scoped.execute(
                        text(
                            "INSERT INTO pages (id, company_id, key, name, created_by) "
                            "VALUES (gen_random_uuid(), :company_id, 'x', 'x', :owner)"
                        ),
                        {"company_id": str(company), "owner": str(owner)},
                    )
