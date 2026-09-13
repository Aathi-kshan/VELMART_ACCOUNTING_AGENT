"""Slice 5 — resolving a name to a real store, user, or linked record,
scoped strictly to the caller's own company. A same-named store/user in a
different company must never be returned.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.entity_tools import SearchEntitiesParams, search_entities
from app.ai.tools.registry import TOOL_REGISTRY
from app.core.context import SecurityContext
from app.models.user import UserRole


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": "d1"}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


async def _owner_headers(client: AsyncClient, owner_password: str) -> dict[str, str]:
    token = await _login(client, "owner@test.lk", owner_password)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def owner_ctx(owner: uuid.UUID, company: uuid.UUID) -> SecurityContext:
    return SecurityContext(user_id=owner, company_id=company, role=UserRole.OWNER, store_ids=())


@pytest.fixture
async def other_company_with_same_named_store(session: AsyncSession) -> uuid.UUID:
    """A second company with a store of the same name as one we'll create in
    the primary company — proof search_entities never crosses the boundary."""
    other_company_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO companies (id, name) VALUES (:id, 'Other Co')"),
        {"id": str(other_company_id)},
    )
    await session.execute(
        text(
            "INSERT INTO stores (id, company_id, code, name) "
            "VALUES (:id, :company_id, 'OTH-1', 'Main Branch')"
        ),
        {"id": str(uuid.uuid4()), "company_id": str(other_company_id)},
    )
    await session.commit()
    return other_company_id


class TestSearchEntitiesStores:
    async def test_finds_a_store_by_fuzzy_name(
        self,
        client: AsyncClient,
        session: AsyncSession,
        owner: uuid.UUID,
        owner_password: str,
        owner_ctx: SecurityContext,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        resp = await client.post(
            "/stores", json={"code": "MAIN-1", "name": "Main Branch"}, headers=headers
        )
        assert resp.status_code == 201, resp.text

        result = await search_entities(
            ctx=owner_ctx,
            session=session,
            params=SearchEntitiesParams(kind="store", query="Main"),
        )

        assert len(result["matches"]) == 1
        assert result["matches"][0]["label"] == "Main Branch"

    async def test_never_returns_another_companys_store(
        self,
        client: AsyncClient,
        session: AsyncSession,
        owner_password: str,
        owner_ctx: SecurityContext,
        other_company_with_same_named_store: uuid.UUID,
    ) -> None:
        result = await search_entities(
            ctx=owner_ctx,
            session=session,
            params=SearchEntitiesParams(kind="store", query="Main Branch"),
        )

        assert result["matches"] == []


class TestSearchEntitiesUsers:
    async def test_finds_a_user_by_fuzzy_name(
        self,
        client: AsyncClient,
        session: AsyncSession,
        manager: uuid.UUID,
        owner_ctx: SecurityContext,
    ) -> None:
        result = await search_entities(
            ctx=owner_ctx,
            session=session,
            params=SearchEntitiesParams(kind="user", query="Test Manager"),
        )

        assert len(result["matches"]) == 1
        assert result["matches"][0]["label"] == "Test Manager"


class TestSearchEntitiesRecordRef:
    async def test_resolves_a_record_on_the_target_page(
        self,
        client: AsyncClient,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        owner_password: str,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_resp = await client.post(
            "/pages",
            json={"name": "Suppliers", "columns": [{"name": "Name", "data_type": "TEXT"}]},
            headers=headers,
        )
        assert page_resp.status_code == 201, page_resp.text
        page = page_resp.json()
        record_resp = await client.post(
            f"/pages/{page['id']}/records",
            json={
                "occurred_at": "2026-01-05T09:00:00Z",
                "data": {"name": "Ceypetco Distributors"},
            },
            headers=headers,
        )
        assert record_resp.status_code == 201, record_resp.text

        result = await search_entities(
            ctx=owner_ctx,
            session=session,
            params=SearchEntitiesParams(kind="record_ref", page_key="suppliers", query="Ceypetco"),
        )

        assert result["page_key"] == "suppliers"
        assert len(result["matches"]) == 1
        assert result["matches"][0]["data"]["name"] == "Ceypetco Distributors"


class TestSearchEntitiesToolPassesSchemaSafety:
    def test_registered_schema_has_no_forbidden_fields(self) -> None:
        tool = TOOL_REGISTRY["search_entities"]
        leaked = {"ctx", "company_id", "user_id", "role"} & tool.schema.get("properties", {}).keys()
        assert not leaked
