"""Configurable dashboard widgets (plan section 15, P5): CRUD, the five
evaluation types (reusing `query_service.py`'s `aggregate`/`query_records`
directly except `TREND`), the manager double-gate (`visible_to` role AND
page view-access), and starter suggestions.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": "d1"}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


async def _owner_headers(client: AsyncClient, owner_password: str) -> dict[str, str]:
    token = await _login(client, "owner@test.lk", owner_password)
    return {"Authorization": f"Bearer {token}"}


async def _manager_headers(client: AsyncClient, manager_password: str) -> dict[str, str]:
    token = await _login(client, "manager@test.lk", manager_password)
    return {"Authorization": f"Bearer {token}"}


async def _create_page(client: AsyncClient, headers: dict[str, str], name: str) -> dict:
    resp = await client.post(
        "/pages",
        json={
            "name": name,
            "columns": [
                {"name": "Amount", "data_type": "CURRENCY", "is_required": True},
                {
                    "name": "Category",
                    "data_type": "SELECT",
                    "config": {"options": ["Rent", "Repair", "Utilities"]},
                },
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _rec(
    client: AsyncClient, headers: dict[str, str], page: dict, *, date: str, amt: str, cat: str
) -> dict:
    resp = await client.post(
        f"/pages/{page['id']}/records",
        json={"occurred_at": f"{date}T10:00:00+05:30", "data": {"amount": amt, "category": cat}},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestWidgetCrud:
    async def test_owner_can_create_a_metric_widget(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers, "Widget CRUD Page")

        resp = await client.post(
            "/dashboard/widgets",
            json={
                "title": "Total spend",
                "widget_type": "METRIC",
                "page_key": page["key"],
                "config": {"metric": "sum", "column": "amount", "period": "current_month"},
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["title"] == "Total spend"

    async def test_manager_cannot_create_a_widget(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, owner_headers, "Manager Cannot Create")

        manager_headers = await _manager_headers(client, manager_password)
        resp = await client.post(
            "/dashboard/widgets",
            json={
                "title": "Nope",
                "widget_type": "METRIC",
                "page_key": page["key"],
                "config": {"metric": "sum", "column": "amount"},
            },
            headers=manager_headers,
        )
        assert resp.status_code == 403

    async def test_create_writes_an_audit_entry(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        company: uuid.UUID, session: AsyncSession,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers, "Audit Widget Page")
        resp = await client.post(
            "/dashboard/widgets",
            json={
                "title": "Audited Widget",
                "widget_type": "LIST",
                "page_key": page["key"],
                "config": {},
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

        row = (
            await session.execute(
                text(
                    "SELECT page_id, new_data FROM audit_logs "
                    "WHERE company_id = :cid AND action = 'DASHBOARD_WIDGET_CREATE' "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"cid": str(company)},
            )
        ).one()
        assert str(row.page_id) == page["id"]
        assert row.new_data["title"] == "Audited Widget"

    async def test_widget_on_a_deleted_page_cascades(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str, session: AsyncSession
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers, "Cascade Test Page")
        create = await client.post(
            "/dashboard/widgets",
            json={
                "title": "Cascades",
                "widget_type": "LIST",
                "page_key": page["key"],
                "config": {},
            },
            headers=headers,
        )
        widget_id = create.json()["id"]

        # A hard delete — the FK's own `ON DELETE CASCADE` (migration 0004),
        # not the app's soft-archive `DELETE /pages/{id}`, which never
        # actually removes the row this constraint would fire on.
        await session.execute(text("DELETE FROM pages WHERE id = :id"), {"id": page["id"]})
        await session.commit()

        remaining = (
            await session.execute(
                text("SELECT count(*) FROM dashboard_widgets WHERE id = :id"), {"id": widget_id}
            )
        ).scalar_one()
        assert remaining == 0


class TestVisibilityDoubleGate:
    async def test_manager_sees_only_widgets_visible_to_their_role(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, owner_headers, "Role Visibility Page")
        await client.put(
            f"/pages/{page['id']}/access",
            json={"grants": [{"user_id": str(manager), "can_view": True, "can_create": True}]},
            headers=owner_headers,
        )
        owner_only = await client.post(
            "/dashboard/widgets",
            json={
                "title": "Owner Only Widget",
                "widget_type": "LIST",
                "page_key": page["key"],
                "config": {},
                "visible_to": "OWNER",
            },
            headers=owner_headers,
        )
        assert owner_only.status_code == 201, owner_only.text
        everyone = await client.post(
            "/dashboard/widgets",
            json={
                "title": "Everyone Widget",
                "widget_type": "LIST",
                "page_key": page["key"],
                "config": {},
            },
            headers=owner_headers,
        )
        assert everyone.status_code == 201, everyone.text

        manager_headers = await _manager_headers(client, manager_password)
        resp = await client.get("/dashboard/widgets", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        titles = {w["title"] for w in resp.json()}
        assert titles == {"Everyone Widget"}

    async def test_manager_sees_only_widgets_on_pages_they_can_view(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        granted_page = await _create_page(client, owner_headers, "Page Visibility Granted")
        ungranted_page = await _create_page(client, owner_headers, "Page Visibility Ungranted")
        await client.put(
            f"/pages/{granted_page['id']}/access",
            json={"grants": [{"user_id": str(manager), "can_view": True, "can_create": True}]},
            headers=owner_headers,
        )
        await client.post(
            "/dashboard/widgets",
            json={
                "title": "On Granted Page",
                "widget_type": "LIST",
                "page_key": granted_page["key"],
                "config": {},
            },
            headers=owner_headers,
        )
        await client.post(
            "/dashboard/widgets",
            json={
                "title": "On Ungranted Page",
                "widget_type": "LIST",
                "page_key": ungranted_page["key"],
                "config": {},
            },
            headers=owner_headers,
        )

        manager_headers = await _manager_headers(client, manager_password)
        resp = await client.get("/dashboard/widgets", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        titles = {w["title"] for w in resp.json()}
        assert titles == {"On Granted Page"}

    async def test_manager_cannot_evaluate_a_widget_hidden_from_their_role(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str,
    ) -> None:
        """The double gate applies to `GET .../data` too, not just the list
        — a manager can't bypass `visible_to` by guessing/enumerating ids."""
        owner_headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, owner_headers, "Hidden Widget Data Page")
        await client.put(
            f"/pages/{page['id']}/access",
            json={"grants": [{"user_id": str(manager), "can_view": True, "can_create": True}]},
            headers=owner_headers,
        )
        create = await client.post(
            "/dashboard/widgets",
            json={
                "title": "Owner Only Data",
                "widget_type": "LIST",
                "page_key": page["key"],
                "config": {},
                "visible_to": "OWNER",
            },
            headers=owner_headers,
        )
        widget_id = create.json()["id"]

        manager_headers = await _manager_headers(client, manager_password)
        resp = await client.get(f"/dashboard/widgets/{widget_id}/data", headers=manager_headers)
        assert resp.status_code == 404


class TestEvaluation:
    async def test_metric_evaluates_current_vs_last_month(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers, "Metric Eval Page")
        await _rec(client, headers, page, date="2026-09-05", amt="100.00", cat="Rent")
        await _rec(client, headers, page, date="2026-09-10", amt="50.00", cat="Repair")

        create = await client.post(
            "/dashboard/widgets",
            json={
                "title": "Total",
                "widget_type": "METRIC",
                "page_key": page["key"],
                "config": {"metric": "sum", "column": "amount", "period": "current_month"},
            },
            headers=headers,
        )
        widget_id = create.json()["id"]

        resp = await client.get(f"/dashboard/widgets/{widget_id}/data", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["widget_type"] == "METRIC"
        assert "comparison_value" in body

    async def test_trend_returns_a_daily_series(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers, "Trend Eval Page")
        await _rec(client, headers, page, date="2026-09-05", amt="10.00", cat="Rent")
        await _rec(client, headers, page, date="2026-09-06", amt="20.00", cat="Rent")

        create = await client.post(
            "/dashboard/widgets",
            json={
                "title": "Daily total",
                "widget_type": "TREND",
                "page_key": page["key"],
                "config": {"column": "amount", "metric": "sum", "bucket": "day", "days": 30},
            },
            headers=headers,
        )
        widget_id = create.json()["id"]

        resp = await client.get(f"/dashboard/widgets/{widget_id}/data", headers=headers)
        assert resp.status_code == 200, resp.text
        series = resp.json()["series"]
        assert len(series) == 2
        assert {Decimal(p["value"]) for p in series} == {Decimal("10.00"), Decimal("20.00")}

    async def test_breakdown_returns_groups(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers, "Breakdown Eval Page")
        await _rec(client, headers, page, date="2026-09-05", amt="10.00", cat="Rent")
        await _rec(client, headers, page, date="2026-09-06", amt="20.00", cat="Repair")
        await _rec(client, headers, page, date="2026-09-07", amt="30.00", cat="Rent")

        create = await client.post(
            "/dashboard/widgets",
            json={
                "title": "By category",
                "widget_type": "BREAKDOWN",
                "page_key": page["key"],
                "config": {"group_by": "category", "metric": "sum", "column": "amount", "top_n": 5},
            },
            headers=headers,
        )
        widget_id = create.json()["id"]

        resp = await client.get(f"/dashboard/widgets/{widget_id}/data", headers=headers)
        assert resp.status_code == 200, resp.text
        groups = {g["key"]: g["value"] for g in resp.json()["groups"]}
        assert groups["Rent"] == "40.00"
        assert groups["Repair"] == "20.00"

    async def test_list_reuses_query_filters(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers, "List Eval Page")
        await _rec(client, headers, page, date="2026-09-05", amt="10.00", cat="Rent")
        await _rec(client, headers, page, date="2026-09-06", amt="20.00", cat="Repair")

        create = await client.post(
            "/dashboard/widgets",
            json={
                "title": "Rent only",
                "widget_type": "LIST",
                "page_key": page["key"],
                "config": {"filters": [{"column": "category", "op": "eq", "value": "Rent"}]},
            },
            headers=headers,
        )
        widget_id = create.json()["id"]

        resp = await client.get(f"/dashboard/widgets/{widget_id}/data", headers=headers)
        assert resp.status_code == 200, resp.text
        records = resp.json()["records"]
        assert len(records) == 1
        assert records[0]["data"]["category"] == "Rent"

    async def test_review_queue_filters_needs_review_true(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers, "Review Queue Eval Page")
        await client.post(
            f"/pages/{page['id']}/validations",
            json={
                "name": "Large amount",
                "expression": "amount <= 15",
                "severity": "WARNING",
                "message": "Amount is unusually large.",
            },
            headers=headers,
        )
        flagged = await _rec(client, headers, page, date="2026-09-05", amt="500.00", cat="Rent")
        await _rec(client, headers, page, date="2026-09-06", amt="5.00", cat="Rent")

        create = await client.post(
            "/dashboard/widgets",
            json={
                "title": "Needs review",
                "widget_type": "REVIEW_QUEUE",
                "page_key": page["key"],
                "config": {},
            },
            headers=headers,
        )
        widget_id = create.json()["id"]

        resp = await client.get(f"/dashboard/widgets/{widget_id}/data", headers=headers)
        assert resp.status_code == 200, resp.text
        records = resp.json()["records"]
        assert len(records) == 1
        assert records[0]["id"] == flagged["id"]


class TestStarterSuggestions:
    async def test_suggestions_cover_the_system_pages_when_no_widgets_exist(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str, system_pages: None
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        resp = await client.get("/dashboard/suggestions", headers=headers)
        assert resp.status_code == 200, resp.text
        page_keys = {s["page_key"] for s in resp.json()}
        assert {"expenses", "daily_revenue", "cheques"}.issubset(page_keys)

    async def test_no_suggestions_once_a_widget_already_exists(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str, system_pages: None
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers, "Suggestion Blocker Page")
        await client.post(
            "/dashboard/widgets",
            json={"title": "Blocker", "widget_type": "LIST", "page_key": page["key"], "config": {}},
            headers=headers,
        )

        resp = await client.get("/dashboard/suggestions", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json() == []
