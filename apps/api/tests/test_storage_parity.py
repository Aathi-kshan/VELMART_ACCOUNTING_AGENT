"""The real proof the storage-dispatch architecture works (plan section
3.5.7): identical filter, sort, and aggregate requests against a system
page (`expenses`, native table) and an Owner-created page holding the same
data, asserting identical results. Nothing in `query_service.py` branches on
which backend it's talking to — if this test passes, that claim is true,
not just documented.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

_ROWS = [
    {"expense_date": "2026-09-01", "expense_name": "Electricity", "amount": "3500.00"},
    {"expense_date": "2026-09-02", "expense_name": "Rent", "amount": "50000.00"},
    {"expense_date": "2026-09-03", "expense_name": "Water", "amount": "1200.00"},
    {"expense_date": "2026-09-04", "expense_name": "Electricity", "amount": "4100.00"},
]


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": "d1"}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


async def _owner_headers(client: AsyncClient, owner_password: str) -> dict[str, str]:
    token = await _login(client, "owner@test.lk", owner_password)
    return {"Authorization": f"Bearer {token}"}


async def _create_mirror_page(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/pages",
        json={
            "name": "Expenses Mirror",
            "columns": [
                {"name": "Expense Date", "data_type": "DATE", "is_required": True},
                {"name": "Expense Name", "data_type": "TEXT", "is_required": True},
                {"name": "Amount", "data_type": "CURRENCY", "is_required": True},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _seed(client: AsyncClient, headers: dict[str, str], page_id: str) -> None:
    for i, row in enumerate(_ROWS):
        resp = await client.post(
            f"/pages/{page_id}/records",
            json={"occurred_at": f"2026-09-0{i + 1}T10:00:00+05:30", "data": row},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text


def _sorted_amounts(items: list[dict[str, object]]) -> list[str]:
    return [str(item["data"]["amount"]) for item in items]  # type: ignore[index]


async def test_filter_and_sort_match_between_system_and_owner_pages(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)
    mirror_page_id = await _create_mirror_page(client, headers)
    await _seed(client, headers, system_page_ids["expenses"])
    await _seed(client, headers, mirror_page_id)

    query = {
        "filters": [{"column": "amount", "op": "gte", "value": "2000.00"}],
        "sort": [{"column": "amount", "direction": "desc"}],
    }
    system_resp = await client.post(
        f"/pages/{system_page_ids['expenses']}/records/query", json=query, headers=headers
    )
    mirror_resp = await client.post(
        f"/pages/{mirror_page_id}/records/query", json=query, headers=headers
    )
    assert system_resp.status_code == 200, system_resp.text
    assert mirror_resp.status_code == 200, mirror_resp.text

    system_amounts = _sorted_amounts(system_resp.json()["items"])
    mirror_amounts = _sorted_amounts(mirror_resp.json()["items"])
    assert system_amounts == mirror_amounts == ["50000.00", "4100.00", "3500.00"]


async def test_aggregate_matches_between_system_and_owner_pages(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)
    mirror_page_id = await _create_mirror_page(client, headers)
    await _seed(client, headers, system_page_ids["expenses"])
    await _seed(client, headers, mirror_page_id)

    aggregate_body = {"metric": "sum", "column": "amount", "group_by": "expense_name"}
    system_resp = await client.post(
        f"/pages/{system_page_ids['expenses']}/aggregate", json=aggregate_body, headers=headers
    )
    mirror_resp = await client.post(
        f"/pages/{mirror_page_id}/aggregate", json=aggregate_body, headers=headers
    )
    assert system_resp.status_code == 200, system_resp.text
    assert mirror_resp.status_code == 200, mirror_resp.text

    system_body = system_resp.json()
    mirror_body = mirror_resp.json()
    assert system_body["value"] == mirror_body["value"] == "58800.00"
    assert system_body["record_count"] == mirror_body["record_count"] == 4

    system_groups = {g["key"]: g["value"] for g in system_body["groups"]}
    mirror_groups = {g["key"]: g["value"] for g in mirror_body["groups"]}
    expected_groups = {"Electricity": "7600.00", "Rent": "50000.00", "Water": "1200.00"}
    assert system_groups == mirror_groups == expected_groups


async def test_column_values_match_between_system_and_owner_pages(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)
    mirror_page_id = await _create_mirror_page(client, headers)
    await _seed(client, headers, system_page_ids["expenses"])
    await _seed(client, headers, mirror_page_id)

    system_resp = await client.get(
        f"/pages/{system_page_ids['expenses']}/column-values/expense_name", headers=headers
    )
    mirror_resp = await client.get(
        f"/pages/{mirror_page_id}/column-values/expense_name", headers=headers
    )
    assert system_resp.status_code == 200, system_resp.text
    assert mirror_resp.status_code == 200, mirror_resp.text
    assert set(system_resp.json()["values"]) == set(mirror_resp.json()["values"]) == {
        "Electricity",
        "Rent",
        "Water",
    }
