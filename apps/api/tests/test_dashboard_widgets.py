"""Configurable dashboard widgets (plan section 15, P5): the five evaluation
types (reusing `query_service.py`'s `aggregate`/`query_records` directly
except `TREND`), and the manager double-gate (`visible_to` role AND page
view-access).

Widget *creation* (`POST /dashboard/widgets`) and the starter-suggestions
endpoint were removed by explicit product decision — an Owner can still view,
edit (`PATCH`), and delete (`DELETE`) a widget, but never create a new one
through the app. Every test below that needs a widget to exist inserts one
directly via SQL (the same pattern `test_permissions_matrix.py`'s
`dashboard_widget` fixture already used) rather than through the API.
"""

from __future__ import annotations

import json
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


async def _insert_widget(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    page_id: str,
    created_by: uuid.UUID,
    title: str,
    widget_type: str,
    config: dict,
    visible_to: str | None = None,
) -> str:
    """Seed a `dashboard_widgets` row directly — the only way to get a
    widget into existence now that `POST /dashboard/widgets` is gone."""
    widget_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO dashboard_widgets "
            "(id, company_id, page_id, title, widget_type, config, visible_to, created_by) "
            "VALUES (:id, :company_id, :page_id, :title, :widget_type, "
            "CAST(:config AS jsonb), :visible_to, :created_by)"
        ),
        {
            "id": str(widget_id),
            "company_id": str(company_id),
            "page_id": page_id,
            "title": title,
            "widget_type": widget_type,
            "config": json.dumps(config),
            "visible_to": visible_to,
            "created_by": str(created_by),
        },
    )
    await session.commit()
    return str(widget_id)


class TestWidgetCascade:
    async def test_widget_on_a_deleted_page_cascades(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        company: uuid.UUID, session: AsyncSession,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers, "Cascade Test Page")
        widget_id = await _insert_widget(
            session,
            company_id=company,
            page_id=page["id"],
            created_by=owner,
            title="Cascades",
            widget_type="LIST",
            config={},
        )

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
        manager: uuid.UUID, manager_password: str, company: uuid.UUID, session: AsyncSession,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, owner_headers, "Role Visibility Page")
        await client.put(
            f"/pages/{page['id']}/access",
            json={"grants": [{"user_id": str(manager), "can_view": True, "can_create": True}]},
            headers=owner_headers,
        )
        await _insert_widget(
            session, company_id=company, page_id=page["id"], created_by=owner,
            title="Owner Only Widget", widget_type="LIST", config={}, visible_to="OWNER",
        )
        await _insert_widget(
            session, company_id=company, page_id=page["id"], created_by=owner,
            title="Everyone Widget", widget_type="LIST", config={},
        )

        manager_headers = await _manager_headers(client, manager_password)
        resp = await client.get("/dashboard/widgets", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        titles = {w["title"] for w in resp.json()}
        assert titles == {"Everyone Widget"}

    async def test_manager_sees_only_widgets_on_pages_they_can_view(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str, company: uuid.UUID, session: AsyncSession,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        granted_page = await _create_page(client, owner_headers, "Page Visibility Granted")
        ungranted_page = await _create_page(client, owner_headers, "Page Visibility Ungranted")
        await client.put(
            f"/pages/{granted_page['id']}/access",
            json={"grants": [{"user_id": str(manager), "can_view": True, "can_create": True}]},
            headers=owner_headers,
        )
        await _insert_widget(
            session, company_id=company, page_id=granted_page["id"], created_by=owner,
            title="On Granted Page", widget_type="LIST", config={},
        )
        await _insert_widget(
            session, company_id=company, page_id=ungranted_page["id"], created_by=owner,
            title="On Ungranted Page", widget_type="LIST", config={},
        )

        manager_headers = await _manager_headers(client, manager_password)
        resp = await client.get("/dashboard/widgets", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        titles = {w["title"] for w in resp.json()}
        assert titles == {"On Granted Page"}

    async def test_manager_cannot_evaluate_a_widget_hidden_from_their_role(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str, company: uuid.UUID, session: AsyncSession,
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
        widget_id = await _insert_widget(
            session, company_id=company, page_id=page["id"], created_by=owner,
            title="Owner Only Data", widget_type="LIST", config={}, visible_to="OWNER",
        )

        manager_headers = await _manager_headers(client, manager_password)
        resp = await client.get(f"/dashboard/widgets/{widget_id}/data", headers=manager_headers)
        assert resp.status_code == 404


class TestEvaluation:
    async def test_metric_evaluates_current_vs_last_month(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        company: uuid.UUID, session: AsyncSession,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers, "Metric Eval Page")
        await _rec(client, headers, page, date="2026-09-05", amt="100.00", cat="Rent")
        await _rec(client, headers, page, date="2026-09-10", amt="50.00", cat="Repair")

        widget_id = await _insert_widget(
            session, company_id=company, page_id=page["id"], created_by=owner,
            title="Total", widget_type="METRIC",
            config={"metric": "sum", "column": "amount", "period": "current_month"},
        )

        resp = await client.get(f"/dashboard/widgets/{widget_id}/data", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["widget_type"] == "METRIC"
        assert "comparison_value" in body

    async def test_trend_returns_a_daily_series(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        company: uuid.UUID, session: AsyncSession,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers, "Trend Eval Page")
        await _rec(client, headers, page, date="2026-09-05", amt="10.00", cat="Rent")
        await _rec(client, headers, page, date="2026-09-06", amt="20.00", cat="Rent")

        widget_id = await _insert_widget(
            session, company_id=company, page_id=page["id"], created_by=owner,
            title="Daily total", widget_type="TREND",
            config={"column": "amount", "metric": "sum", "bucket": "day", "days": 30},
        )

        resp = await client.get(f"/dashboard/widgets/{widget_id}/data", headers=headers)
        assert resp.status_code == 200, resp.text
        series = resp.json()["series"]
        assert len(series) == 2
        assert {Decimal(p["value"]) for p in series} == {Decimal("10.00"), Decimal("20.00")}

    async def test_breakdown_returns_groups(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        company: uuid.UUID, session: AsyncSession,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers, "Breakdown Eval Page")
        await _rec(client, headers, page, date="2026-09-05", amt="10.00", cat="Rent")
        await _rec(client, headers, page, date="2026-09-06", amt="20.00", cat="Repair")
        await _rec(client, headers, page, date="2026-09-07", amt="30.00", cat="Rent")

        widget_id = await _insert_widget(
            session, company_id=company, page_id=page["id"], created_by=owner,
            title="By category", widget_type="BREAKDOWN",
            config={"group_by": "category", "metric": "sum", "column": "amount", "top_n": 5},
        )

        resp = await client.get(f"/dashboard/widgets/{widget_id}/data", headers=headers)
        assert resp.status_code == 200, resp.text
        groups = {g["key"]: g["value"] for g in resp.json()["groups"]}
        assert groups["Rent"] == "40.00"
        assert groups["Repair"] == "20.00"

    async def test_list_reuses_query_filters(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        company: uuid.UUID, session: AsyncSession,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers, "List Eval Page")
        await _rec(client, headers, page, date="2026-09-05", amt="10.00", cat="Rent")
        await _rec(client, headers, page, date="2026-09-06", amt="20.00", cat="Repair")

        widget_id = await _insert_widget(
            session, company_id=company, page_id=page["id"], created_by=owner,
            title="Rent only", widget_type="LIST",
            config={"filters": [{"column": "category", "op": "eq", "value": "Rent"}]},
        )

        resp = await client.get(f"/dashboard/widgets/{widget_id}/data", headers=headers)
        assert resp.status_code == 200, resp.text
        records = resp.json()["records"]
        assert len(records) == 1
        assert records[0]["data"]["category"] == "Rent"

    async def test_review_queue_filters_needs_review_true(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        company: uuid.UUID, session: AsyncSession,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers, "Review Queue Eval Page")
        flagged = await _rec(client, headers, page, date="2026-09-05", amt="500.00", cat="Rent")
        await _rec(client, headers, page, date="2026-09-06", amt="5.00", cat="Rent")

        # Validation rules (the feature that used to set this) are gone —
        # flag the record directly, the same platform field either way.
        await session.execute(
            text("UPDATE records SET needs_review = true WHERE id = :id"),
            {"id": flagged["id"]},
        )
        await session.commit()

        widget_id = await _insert_widget(
            session, company_id=company, page_id=page["id"], created_by=owner,
            title="Needs review", widget_type="REVIEW_QUEUE", config={},
        )

        resp = await client.get(f"/dashboard/widgets/{widget_id}/data", headers=headers)
        assert resp.status_code == 200, resp.text
        records = resp.json()["records"]
        assert len(records) == 1
        assert records[0]["id"] == flagged["id"]
