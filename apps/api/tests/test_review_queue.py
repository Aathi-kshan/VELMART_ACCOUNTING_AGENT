"""Review queue filtering (plan section 11.6, P4 §9): `needs_review` and
`status` are real columns on every record but never entries in a page's own
`page_columns` — `resolve_column` treats them as platform fields so
`POST /pages/{id}/records/query` can filter (and sort) by them through the
same path as any other column, with no separate plumbing.
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
            "name": "Revenue Review",
            "columns": [
                {"name": "Amount", "data_type": "CURRENCY", "is_required": True},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _add_warning_rule(client: AsyncClient, headers: dict[str, str], page_id: str) -> None:
    resp = await client.post(
        f"/pages/{page_id}/validations",
        json={
            "name": "Large amount",
            "expression": "amount <= 100",
            "severity": "WARNING",
            "message": "Amount exceeds the normal range.",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


async def _create_record(
    client: AsyncClient, headers: dict[str, str], page_id: str, *, amount: str
) -> dict:
    resp = await client.post(
        f"/pages/{page_id}/records",
        json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"amount": amount}},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestNeedsReviewFilter:
    async def test_filtering_by_needs_review_true_returns_exactly_the_flagged_records(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        await _add_warning_rule(client, headers, page_id)

        flagged = await _create_record(client, headers, page_id, amount="500.00")
        assert flagged["needs_review"] is True
        clean = await _create_record(client, headers, page_id, amount="10.00")
        assert clean["needs_review"] is False

        resp = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "needs_review", "op": "eq", "value": True}]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert {i["id"] for i in items} == {flagged["id"]}

    async def test_filtering_by_needs_review_false_returns_the_rest(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        await _add_warning_rule(client, headers, page_id)

        await _create_record(client, headers, page_id, amount="500.00")
        clean = await _create_record(client, headers, page_id, amount="10.00")

        resp = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "needs_review", "op": "eq", "value": False}]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert {i["id"] for i in items} == {clean["id"]}


class TestStatusFilter:
    async def test_filtering_by_status_behaves_the_same_way(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        active = await _create_record(client, headers, page_id, amount="10.00")
        assert active["status"] == "ACTIVE"

        resp = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "status", "op": "eq", "value": "ACTIVE"}]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert {i["id"] for i in resp.json()["items"]} == {active["id"]}

        resp_reversed = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "status", "op": "eq", "value": "REVERSED"}]},
            headers=headers,
        )
        assert resp_reversed.status_code == 200, resp_reversed.text
        assert resp_reversed.json()["items"] == []
