"""Slice 3 — schema discovery tools never assume a business's table names.

A page is built through the public API with a deliberately non-obvious name
("Fuel Log", not "Expenses") — proof that `list_pages`/`get_page_schema`/
`get_column_values` describe whatever a business actually has, rather than a
shape these tools happen to know about in advance.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.discovery_tools import (
    GetColumnValuesParams,
    GetPageSchemaParams,
    ListPagesParams,
    get_column_values,
    get_page_schema,
    list_pages,
)
from app.ai.tools.registry import TOOL_REGISTRY
from app.core.context import SecurityContext
from app.core.errors import NotFoundError
from app.models.user import UserRole


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": "d1"}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


@pytest.fixture
async def fuel_log_page(
    client: AsyncClient, owner: uuid.UUID, owner_password: str
) -> dict:
    token = await _login(client, "owner@test.lk", owner_password)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        "/pages",
        json={
            "name": "Fuel Log",
            "columns": [
                {"name": "Vehicle", "data_type": "TEXT"},
                {"name": "Litres", "data_type": "NUMBER"},
                {"name": "Cost", "data_type": "CURRENCY"},
                {
                    "name": "Station",
                    "data_type": "SELECT",
                    "config": {"options": ["Ceypetco", "Lanka IOC"]},
                },
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    page = resp.json()

    for vehicle, litres, cost, station, occurred_at in (
        ("Van 1", "40", "12000.00", "Ceypetco", "2026-01-05T09:00:00Z"),
        ("Van 2", "35", "10500.00", "Lanka IOC", "2026-01-10T09:00:00Z"),
    ):
        create_resp = await client.post(
            f"/pages/{page['id']}/records",
            json={
                "occurred_at": occurred_at,
                "data": {"vehicle": vehicle, "litres": litres, "cost": cost, "station": station},
            },
            headers=headers,
        )
        assert create_resp.status_code == 201, create_resp.text

    return page


@pytest.fixture
def owner_ctx(owner: uuid.UUID, company: uuid.UUID) -> SecurityContext:
    return SecurityContext(user_id=owner, company_id=company, role=UserRole.OWNER, store_ids=())


class TestListPages:
    async def test_finds_the_arbitrarily_named_page(
        self, session: AsyncSession, owner_ctx: SecurityContext, fuel_log_page: dict
    ) -> None:
        pages = await list_pages(ctx=owner_ctx, session=session, params=ListPagesParams())

        fuel_log = next(p for p in pages if p["page_key"] == "fuel_log")
        assert fuel_log["name"] == "Fuel Log"
        assert fuel_log["record_count"] == 2
        assert fuel_log["date_range"]["from"] == "2026-01-05"
        assert fuel_log["date_range"]["to"] == "2026-01-10"


class TestGetPageSchema:
    async def test_returns_real_columns_not_a_hardcoded_shape(
        self, session: AsyncSession, owner_ctx: SecurityContext, fuel_log_page: dict
    ) -> None:
        result = await get_page_schema(
            ctx=owner_ctx, session=session, params=GetPageSchemaParams(page_key="fuel_log")
        )

        columns_by_key = {c["key"]: c for c in result["columns"]}
        assert columns_by_key["vehicle"]["data_type"] == "TEXT"
        assert columns_by_key["litres"]["data_type"] == "NUMBER"
        assert columns_by_key["cost"]["data_type"] == "CURRENCY"
        assert columns_by_key["station"]["data_type"] == "SELECT"
        assert columns_by_key["station"]["options"] == ["Ceypetco", "Lanka IOC"]

    async def test_unknown_page_key_raises_not_found(
        self, session: AsyncSession, owner_ctx: SecurityContext
    ) -> None:
        with pytest.raises(NotFoundError):
            await get_page_schema(
                ctx=owner_ctx, session=session, params=GetPageSchemaParams(page_key="no_such_page")
            )


class TestGetColumnValues:
    async def test_returns_observed_values_for_a_text_column(
        self, session: AsyncSession, owner_ctx: SecurityContext, fuel_log_page: dict
    ) -> None:
        result = await get_column_values(
            ctx=owner_ctx,
            session=session,
            params=GetColumnValuesParams(page_key="fuel_log", column_key="vehicle"),
        )

        assert set(result["values"]) == {"Van 1", "Van 2"}

    async def test_returns_select_options_for_a_select_column(
        self, session: AsyncSession, owner_ctx: SecurityContext, fuel_log_page: dict
    ) -> None:
        result = await get_column_values(
            ctx=owner_ctx,
            session=session,
            params=GetColumnValuesParams(page_key="fuel_log", column_key="station"),
        )

        assert set(result["values"]) == {"Ceypetco", "Lanka IOC"}


class TestDiscoveryToolsPassSchemaSafety:
    def test_registered_schemas_have_no_forbidden_fields(self) -> None:
        for tool_name in ("list_pages", "get_page_schema", "get_column_values"):
            tool = TOOL_REGISTRY[tool_name]
            leaked = {"ctx", "company_id", "user_id", "role"} & tool.schema.get(
                "properties", {}
            ).keys()
            assert not leaked, f"{tool_name} leaks {leaked}"
