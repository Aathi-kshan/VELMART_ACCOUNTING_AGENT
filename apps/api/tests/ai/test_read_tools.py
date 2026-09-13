"""Slice 4 — query, filter, sort, search, aggregate, and formula tools.

Every number these tools return must be computed by Postgres or the safe
expression evaluator, never by the model — checked here against a fixture
page with known data, built through the public API.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.read_tools import (
    AggregateRecordsParams,
    CalculateFormulaParams,
    FilterRecordsParams,
    QueryRecordsParams,
    SearchRecordsParams,
    SortRecordsParams,
    aggregate_records,
    calculate_formula,
    filter_records,
    query_records,
    search_records,
    sort_records,
)
from app.core.context import SecurityContext
from app.core.errors import ValidationFailedError
from app.models.user import UserRole
from app.schemas.common import QueryFilter, SortSpec


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
async def vehicle_costs_page(client: AsyncClient, owner: uuid.UUID, owner_password: str) -> dict:
    headers = await _owner_headers(client, owner_password)
    resp = await client.post(
        "/pages",
        json={
            "name": "Vehicle Costs",
            "columns": [
                {"name": "Vehicle", "data_type": "TEXT"},
                {"name": "Amount", "data_type": "CURRENCY"},
                {
                    "name": "Category",
                    "data_type": "SELECT",
                    "config": {"options": ["Fuel", "Repair"]},
                },
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    page = resp.json()

    rows = (
        ("Van 1", "12000.00", "Fuel", "2026-01-05T09:00:00Z"),
        ("Van 2", "10500.00", "Fuel", "2026-01-10T09:00:00Z"),
        ("Van 1", "5000.00", "Repair", "2026-01-15T09:00:00Z"),
    )
    for vehicle, amount, category, occurred_at in rows:
        create_resp = await client.post(
            f"/pages/{page['id']}/records",
            json={
                "occurred_at": occurred_at,
                "data": {"vehicle": vehicle, "amount": amount, "category": category},
            },
            headers=headers,
        )
        assert create_resp.status_code == 201, create_resp.text

    return page


@pytest.fixture
async def fuel_log_page(client: AsyncClient, owner: uuid.UUID, owner_password: str) -> dict:
    """A second, unrelated page — used to prove search_records' no-page_key
    fan-out finds a match on the *right* page among several."""
    headers = await _owner_headers(client, owner_password)
    resp = await client.post(
        "/pages",
        json={"name": "Fuel Log", "columns": [{"name": "Notes", "data_type": "LONG_TEXT"}]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    page = resp.json()
    create_resp = await client.post(
        f"/pages/{page['id']}/records",
        json={
            "occurred_at": "2026-01-06T09:00:00Z",
            "data": {"notes": "Topped up Van 3 at Ceypetco"},
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    return page


@pytest.fixture
def owner_ctx(owner: uuid.UUID, company: uuid.UUID) -> SecurityContext:
    return SecurityContext(user_id=owner, company_id=company, role=UserRole.OWNER, store_ids=())


class TestAggregateRecords:
    async def test_sum_matches_hand_computed_total(
        self, session: AsyncSession, owner_ctx: SecurityContext, vehicle_costs_page: dict
    ) -> None:
        result = await aggregate_records(
            ctx=owner_ctx,
            session=session,
            params=AggregateRecordsParams(
                page_key="vehicle_costs", metric="sum", column_key="amount"
            ),
        )

        assert Decimal(result["value"]) == Decimal("27500.00")
        assert result["record_count"] == 3

    async def test_grouped_by_category(
        self, session: AsyncSession, owner_ctx: SecurityContext, vehicle_costs_page: dict
    ) -> None:
        result = await aggregate_records(
            ctx=owner_ctx,
            session=session,
            params=AggregateRecordsParams(
                page_key="vehicle_costs", metric="sum", column_key="amount", group_by="category"
            ),
        )

        by_key = {g["key"]: Decimal(g["value"]) for g in result["groups"]}
        assert by_key["Fuel"] == Decimal("22500.00")
        assert by_key["Repair"] == Decimal("5000.00")

    async def test_unknown_column_raises_clean_error_not_raw_sql(
        self, session: AsyncSession, owner_ctx: SecurityContext, vehicle_costs_page: dict
    ) -> None:
        with pytest.raises(ValidationFailedError):
            await aggregate_records(
                ctx=owner_ctx,
                session=session,
                params=AggregateRecordsParams(
                    page_key="vehicle_costs", metric="sum", column_key="not_a_real_column"
                ),
            )


class TestQueryFilterSortRecords:
    async def test_query_records_returns_expected_rows(
        self, session: AsyncSession, owner_ctx: SecurityContext, vehicle_costs_page: dict
    ) -> None:
        result = await query_records(
            ctx=owner_ctx,
            session=session,
            params=QueryRecordsParams(
                page_key="vehicle_costs",
                filters=[QueryFilter(column="category", op="eq", value="Fuel")],
            ),
        )

        assert len(result["items"]) == 2
        assert {item["data"]["vehicle"] for item in result["items"]} == {"Van 1", "Van 2"}

    async def test_filter_records_matches_known_filter(
        self, session: AsyncSession, owner_ctx: SecurityContext, vehicle_costs_page: dict
    ) -> None:
        result = await filter_records(
            ctx=owner_ctx,
            session=session,
            params=FilterRecordsParams(
                page_key="vehicle_costs",
                filters=[QueryFilter(column="vehicle", op="eq", value="Van 1")],
            ),
        )

        assert len(result["items"]) == 2
        assert all(item["data"]["vehicle"] == "Van 1" for item in result["items"])

    async def test_sort_records_orders_by_amount(
        self, session: AsyncSession, owner_ctx: SecurityContext, vehicle_costs_page: dict
    ) -> None:
        result = await sort_records(
            ctx=owner_ctx,
            session=session,
            params=SortRecordsParams(
                page_key="vehicle_costs", sort=[SortSpec(column="amount", direction="desc")]
            ),
        )

        amounts = [Decimal(item["data"]["amount"]) for item in result["items"]]
        assert amounts == sorted(amounts, reverse=True)

    async def test_over_max_limit_is_rejected_not_silently_truncated(self) -> None:
        with pytest.raises(ValidationError):
            QueryRecordsParams(page_key="vehicle_costs", limit=501)


class TestSearchRecords:
    async def test_page_scoped_search(
        self, session: AsyncSession, owner_ctx: SecurityContext, vehicle_costs_page: dict
    ) -> None:
        result = await search_records(
            ctx=owner_ctx,
            session=session,
            params=SearchRecordsParams(query="Van 2", page_key="vehicle_costs"),
        )

        assert "vehicle_costs" in result["matches_by_page"]
        assert len(result["matches_by_page"]["vehicle_costs"]) == 1

    async def test_fans_out_and_finds_the_right_page(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        vehicle_costs_page: dict,
        fuel_log_page: dict,
    ) -> None:
        result = await search_records(
            ctx=owner_ctx, session=session, params=SearchRecordsParams(query="Ceypetco")
        )

        assert set(result["matches_by_page"]) == {"fuel_log"}


class TestCalculateFormula:
    async def test_matches_hand_computed_result(self) -> None:
        result = await calculate_formula(
            ctx=None,  # type: ignore[arg-type]
            session=None,  # type: ignore[arg-type]
            params=CalculateFormulaParams(
                expression="(current - previous) / previous * 100",
                operands={"current": "1200.00", "previous": "1000.00"},
            ),
        )

        assert Decimal(result["result"]) == Decimal("20.00")

    async def test_rejects_disallowed_syntax_never_reaches_eval(self) -> None:
        with pytest.raises(ValidationFailedError):
            await calculate_formula(
                ctx=None,  # type: ignore[arg-type]
                session=None,  # type: ignore[arg-type]
                params=CalculateFormulaParams(
                    expression="__import__('os').system('echo hi')", operands={}
                ),
            )
