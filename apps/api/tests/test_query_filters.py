"""Query, aggregation, and column-value discovery (plan sections 3.8, 3.9;
docs/API.md §5). The `TestInjectionSafety` class is the actual proof behind
the name: a malicious `column` string is rejected as an unknown column,
never reaches SQL.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": "d1"}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


async def _owner_headers(client: AsyncClient, owner_password: str) -> dict[str, str]:
    token = await _login(client, "owner@test.lk", owner_password)
    return {"Authorization": f"Bearer {token}"}


async def _create_page(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/pages",
        json={
            "name": "Outgoings",
            "columns": [
                {"name": "Date", "data_type": "DATE", "is_required": True, "is_indexed": True},
                {
                    "name": "Category",
                    "data_type": "SELECT",
                    "config": {"options": ["Electricity", "Rent", "Transport"]},
                },
                {
                    "name": "Amount",
                    "data_type": "CURRENCY",
                    "is_required": True,
                    "is_indexed": True,
                },
                {"name": "Note", "data_type": "TEXT"},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _add_record(
    client: AsyncClient,
    headers: dict[str, str],
    page_id: str,
    *,
    date: str,
    category: str | None,
    amount: str,
    note: str = "",
) -> dict:
    data: dict[str, str] = {"date": date, "amount": amount, "note": note}
    if category is not None:
        # Omitted entirely, not "", so a null-category record actually means
        # "no value supplied" — SELECT's Literal validation rejects "" since
        # it isn't one of the configured options.
        data["category"] = category
    resp = await client.post(
        f"/pages/{page_id}/records",
        json={"occurred_at": f"{date}T10:00:00+05:30", "data": data},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestFilterOperators:
    async def test_eq(self, client: AsyncClient, owner: uuid.UUID, owner_password: str) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        await _add_record(
            client,
            headers,
            page_id,
            date="2026-09-01",
            category="Rent",
            amount="100.00",
        )
        await _add_record(
            client, headers, page_id, date="2026-09-02", category="Electricity", amount="50.00"
        )

        resp = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "category", "op": "eq", "value": "Rent"}]},
            headers=headers,
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["data"]["category"] == "Rent"

    async def test_neq(self, client: AsyncClient, owner: uuid.UUID, owner_password: str) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        await _add_record(
            client,
            headers,
            page_id,
            date="2026-09-01",
            category="Rent",
            amount="100.00",
        )
        await _add_record(
            client, headers, page_id, date="2026-09-02", category="Electricity", amount="50.00"
        )

        resp = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "category", "op": "neq", "value": "Rent"}]},
            headers=headers,
        )
        assert {i["data"]["category"] for i in resp.json()["items"]} == {"Electricity"}

    async def test_gt_gte_lt_lte(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        for amount in ("10.00", "20.00", "30.00"):
            await _add_record(
                client, headers, page_id, date="2026-09-01", category="Rent", amount=amount
            )

        gt = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "amount", "op": "gt", "value": "20.00"}]},
            headers=headers,
        )
        assert {i["data"]["amount"] for i in gt.json()["items"]} == {"30.00"}

        gte = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "amount", "op": "gte", "value": "20.00"}]},
            headers=headers,
        )
        assert {i["data"]["amount"] for i in gte.json()["items"]} == {"20.00", "30.00"}

        lt = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "amount", "op": "lt", "value": "20.00"}]},
            headers=headers,
        )
        assert {i["data"]["amount"] for i in lt.json()["items"]} == {"10.00"}

        lte = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "amount", "op": "lte", "value": "20.00"}]},
            headers=headers,
        )
        assert {i["data"]["amount"] for i in lte.json()["items"]} == {"10.00", "20.00"}

    async def test_between(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        for amount in ("10.00", "20.00", "30.00"):
            await _add_record(
                client, headers, page_id, date="2026-09-01", category="Rent", amount=amount
            )

        resp = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "amount", "op": "between", "value": ["15.00", "25.00"]}]},
            headers=headers,
        )
        assert {i["data"]["amount"] for i in resp.json()["items"]} == {"20.00"}

    async def test_in(self, client: AsyncClient, owner: uuid.UUID, owner_password: str) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        await _add_record(
            client,
            headers,
            page_id,
            date="2026-09-01",
            category="Rent",
            amount="1.00",
        )
        await _add_record(
            client, headers, page_id, date="2026-09-02", category="Electricity", amount="1.00"
        )
        await _add_record(
            client, headers, page_id, date="2026-09-03", category="Transport", amount="1.00"
        )

        resp = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "category", "op": "in", "value": ["Rent", "Transport"]}]},
            headers=headers,
        )
        assert {i["data"]["category"] for i in resp.json()["items"]} == {"Rent", "Transport"}

    async def test_contains(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        await _add_record(
            client, headers, page_id, date="2026-09-01", category="Rent", amount="1.00",
            note="paid via CEB office",
        )
        await _add_record(
            client, headers, page_id, date="2026-09-02", category="Rent", amount="1.00",
            note="other",
        )

        resp = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "note", "op": "contains", "value": "CEB"}]},
            headers=headers,
        )
        assert len(resp.json()["items"]) == 1

    async def test_is_null(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        await _add_record(
            client,
            headers,
            page_id,
            date="2026-09-01",
            category="Rent",
            amount="1.00",
        )
        await _add_record(
            client, headers, page_id, date="2026-09-02", category=None, amount="1.00"
        )

        resp = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "category", "op": "is_null", "value": None}]},
            headers=headers,
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        # Present with a null value (not omitted) — SELECT has no configured
        # `default`, so the field stays in `data` as null rather than absent
        # (unlike FORMULA, which is excluded from the schema model entirely).
        assert items[0]["data"]["category"] is None


class TestSearch:
    async def test_trigram_search_across_record_text(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        await _add_record(
            client, headers, page_id, date="2026-09-01", category="Rent", amount="1.00",
            note="Ceylon Electricity Board",
        )
        await _add_record(
            client, headers, page_id, date="2026-09-02", category="Rent", amount="1.00",
            note="unrelated",
        )

        resp = await client.post(
            f"/pages/{page_id}/records/query",
            json={"search": "Electricity Board"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1


class TestPagination:
    async def test_cursor_pagination_covers_every_record_exactly_once(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        created_ids = set()
        for day in range(1, 6):
            record = await _add_record(
                client,
                headers,
                page_id,
                date=f"2026-09-{day:02d}",
                category="Rent",
                amount="1.00",
            )
            created_ids.add(record["id"])

        seen_ids: set[str] = set()
        cursor = None
        pages_fetched = 0
        while True:
            resp = await client.post(
                f"/pages/{page_id}/records/query",
                json={"limit": 2, **({"cursor": cursor} if cursor else {})},
                headers=headers,
            )
            assert resp.status_code == 200
            body = resp.json()
            for item in body["items"]:
                assert item["id"] not in seen_ids, "duplicate record across pages"
                seen_ids.add(item["id"])
            pages_fetched += 1
            assert pages_fetched < 10, "pagination did not terminate"
            if not body["has_more"]:
                break
            cursor = body["next_cursor"]

        assert seen_ids == created_ids


class TestAggregate:
    async def test_sum_with_group_by_and_period(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        await _add_record(
            client, headers, page_id, date="2026-09-01", category="Electricity", amount="500.00"
        )
        await _add_record(
            client, headers, page_id, date="2026-09-02", category="Electricity", amount="300.00"
        )
        await _add_record(
            client, headers, page_id, date="2026-09-03", category="Rent", amount="1000.00"
        )

        resp = await client.post(
            f"/pages/{page_id}/aggregate",
            json={
                "metric": "sum",
                "column": "amount",
                "group_by": "category",
                "filters": [{"column": "category", "op": "eq", "value": "Electricity"}],
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["value"] == "800.00"
        assert body["record_count"] == 2
        assert body["groups"] == [{"key": "Electricity", "value": "800.00", "count": 2}]

    async def test_count_with_no_column(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        await _add_record(
            client,
            headers,
            page_id,
            date="2026-09-01",
            category="Rent",
            amount="1.00",
        )
        await _add_record(
            client,
            headers,
            page_id,
            date="2026-09-02",
            category="Rent",
            amount="1.00",
        )

        resp = await client.post(
            f"/pages/{page_id}/aggregate", json={"metric": "count"}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["record_count"] == 2


class TestColumnValues:
    async def test_select_column_returns_configured_options(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        resp = await client.get(f"/pages/{page_id}/column-values/category", headers=headers)
        assert resp.status_code == 200
        assert set(resp.json()["values"]) == {"Electricity", "Rent", "Transport"}

    async def test_text_column_returns_observed_values(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        await _add_record(
            client, headers, page_id, date="2026-09-01", category="Rent", amount="1.00", note="A"
        )
        await _add_record(
            client, headers, page_id, date="2026-09-02", category="Rent", amount="1.00", note="B"
        )

        resp = await client.get(f"/pages/{page_id}/column-values/note", headers=headers)
        assert resp.status_code == 200
        assert set(resp.json()["values"]) == {"A", "B"}


class TestInjectionSafety:
    async def test_unknown_column_in_filter_is_rejected_not_executed(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        await _add_record(
            client,
            headers,
            page_id,
            date="2026-09-01",
            category="Rent",
            amount="1.00",
        )

        malicious = "amount; DROP TABLE records; --"
        resp = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": malicious, "op": "eq", "value": "1"}]},
            headers=headers,
        )
        assert resp.status_code == 422

        # The table must still exist and still hold the one record.
        confirm = await client.post(
            f"/pages/{page_id}/records/query", json={}, headers=headers
        )
        assert confirm.status_code == 200
        assert len(confirm.json()["items"]) == 1

    async def test_unknown_column_in_sort_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        resp = await client.post(
            f"/pages/{page_id}/records/query",
            json={"sort": [{"column": "'; DROP TABLE records; --", "direction": "asc"}]},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_unknown_column_in_group_by_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        resp = await client.post(
            f"/pages/{page_id}/aggregate",
            json={"metric": "count", "group_by": "amount) FROM records; --"},
            headers=headers,
        )
        assert resp.status_code == 422
