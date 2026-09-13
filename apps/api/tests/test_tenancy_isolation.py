"""Company A can never read or write company B's data (plan section 24.2) —
checked at both walls: the repository layer's own `WHERE company_id = ...`
(app/repositories/base.py), and Postgres RLS itself (migration 0006), which
must hold even if a query forgets to filter by company_id.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import set_rls_context
from app.models.store import Store
from app.repositories.base import get_for_company, list_for_company


@pytest.fixture
async def company_b(session: AsyncSession) -> uuid.UUID:
    company_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO companies (id, name) VALUES (:id, 'Other Supermarket')"),
        {"id": str(company_id)},
    )
    await session.commit()
    return company_id


@pytest.fixture
async def store_in_a(session: AsyncSession, company: uuid.UUID) -> uuid.UUID:
    store_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO stores (id, company_id, code, name) "
            "VALUES (:id, :company_id, 'A1', 'Store A1')"
        ),
        {"id": str(store_id), "company_id": str(company)},
    )
    await session.commit()
    return store_id


@pytest.fixture
async def store_in_b(session: AsyncSession, company_b: uuid.UUID) -> uuid.UUID:
    store_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO stores (id, company_id, code, name) "
            "VALUES (:id, :company_id, 'B1', 'Store B1')"
        ),
        {"id": str(store_id), "company_id": str(company_b)},
    )
    await session.commit()
    return store_id


class TestRepositoryLayer:
    """Unit-level: the same two calls every service in app/services/ makes,
    against two different SecurityContexts' company_id. Runs on the
    superuser `session` fixture on purpose — RLS never applies to it, so a
    pass here proves app/repositories/base.py's own WHERE clause is correct
    on its own, independent of the RLS backstop below."""

    async def test_get_for_company_never_returns_another_companys_row(
        self,
        session: AsyncSession,
        company: uuid.UUID,
        store_in_a: uuid.UUID,
        store_in_b: uuid.UUID,
    ) -> None:
        assert await get_for_company(session, Store, store_in_b, company) is None
        found = await get_for_company(session, Store, store_in_a, company)
        assert found is not None
        assert found.id == store_in_a

    async def test_list_for_company_only_lists_its_own_rows(
        self,
        session: AsyncSession,
        company: uuid.UUID,
        store_in_a: uuid.UUID,
        store_in_b: uuid.UUID,
    ) -> None:
        rows = await list_for_company(session, Store, company)
        assert {r.id for r in rows} == {store_in_a}


class TestRlsLayer:
    """RLS-level: connected as app_user (the role the running app actually
    uses), a query that does NOT filter by company_id at all is still
    refused — proving RLS is a real second wall, not just an untested claim
    resting on the repository layer always remembering to filter."""

    async def test_unfiltered_query_cannot_see_another_companys_row(
        self,
        app_user_session: AsyncSession,
        company: uuid.UUID,
        store_in_a: uuid.UUID,
        store_in_b: uuid.UUID,
    ) -> None:
        async with app_user_session.begin():
            await set_rls_context(app_user_session, company_id=company, role="OWNER")
            # Deliberately unscoped — no `AND company_id = ...` — to prove
            # the database itself refuses this, not the query's own filter.
            result = await app_user_session.execute(
                text("SELECT id FROM stores WHERE id = :id"), {"id": str(store_in_b)}
            )
            assert result.scalar_one_or_none() is None

            result = await app_user_session.execute(
                text("SELECT id FROM stores WHERE id = :id"), {"id": str(store_in_a)}
            )
            assert result.scalar_one_or_none() == store_in_a


class TestHttpLayer:
    """End-to-end: company A's real access token, through the real app,
    against a store that belongs to company B."""

    async def test_owner_cannot_patch_another_companys_store(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        store_in_b: uuid.UUID,
    ) -> None:
        login = await client.post(
            "/auth/login",
            json={"email": "owner@test.lk", "password": owner_password, "device_id": "d1"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        resp = await client.patch(
            f"/stores/{store_in_b}",
            json={"name": "Hijacked"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_owner_cannot_see_another_companys_store_in_list(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        store_in_a: uuid.UUID,
        store_in_b: uuid.UUID,
    ) -> None:
        login = await client.post(
            "/auth/login",
            json={"email": "owner@test.lk", "password": owner_password, "device_id": "d1"},
        )
        token = login.json()["access_token"]

        resp = await client.get("/stores", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        ids = {row["id"] for row in resp.json()}
        assert ids == {str(store_in_a)}
