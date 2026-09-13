"""`GET /reconciliation` (plan sections 3.5.11, 12.5; docs/API.md §1.8) —
compares `daily_revenue` against `cash_ledger` for the same business date via
the `daily_reconciliation` view. A manager needs `view` on *both* system
pages or gets 404; an owner always can.
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


async def _manager_headers(client: AsyncClient, manager_password: str) -> dict[str, str]:
    token = await _login(client, "manager@test.lk", manager_password)
    return {"Authorization": f"Bearer {token}"}


async def _grant(
    client: AsyncClient, owner_headers: dict[str, str], page_id: str, user_id: uuid.UUID
) -> None:
    resp = await client.put(
        f"/pages/{page_id}/access",
        json={"grants": [{"user_id": str(user_id), "can_view": True, "can_create": True}]},
        headers=owner_headers,
    )
    assert resp.status_code == 200, resp.text


async def _create(
    client: AsyncClient, headers: dict[str, str], page_id: str, occurred_at: str, data: dict
) -> None:
    resp = await client.post(
        f"/pages/{page_id}/records",
        json={"occurred_at": occurred_at, "data": data},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


async def test_matching_totals_reconcile_to_zero(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)
    await _create(
        client,
        headers,
        system_page_ids["daily_revenue"],
        "2026-09-03T20:00:00+05:30",
        {"entry_date": "2026-09-03", "cash_sales": "10000.00", "card_sales": "5000.00"},
    )
    await _create(
        client,
        headers,
        system_page_ids["cash_ledger"],
        "2026-09-03T20:00:00+05:30",
        {"entry_date": "2026-09-03", "cash_amount": "10000.00", "card_sales_amount": "5000.00"},
    )

    resp = await client.get("/reconciliation", headers=headers)
    assert resp.status_code == 200, resp.text
    items = {i["business_date"]: i for i in resp.json()["items"]}
    assert items["2026-09-03"]["revenue_total"] == "15000.00"
    assert items["2026-09-03"]["ledger_total"] == "15000.00"
    assert items["2026-09-03"]["difference"] == "0.00"


async def test_worked_example_from_the_plan(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)
    await _create(
        client,
        headers,
        system_page_ids["daily_revenue"],
        "2026-09-04T20:00:00+05:30",
        {"entry_date": "2026-09-04", "cash_sales": "150000.00", "card_sales": "100000.00"},
    )
    await _create(
        client,
        headers,
        system_page_ids["cash_ledger"],
        "2026-09-04T20:00:00+05:30",
        {"entry_date": "2026-09-04", "cash_amount": "150000.00", "card_sales_amount": "98000.00"},
    )

    resp = await client.get("/reconciliation", headers=headers)
    assert resp.status_code == 200, resp.text
    item = next(i for i in resp.json()["items"] if i["business_date"] == "2026-09-04")
    assert item["revenue_total"] == "250000.00"
    assert item["ledger_total"] == "248000.00"
    assert item["difference"] == "2000.00"


async def test_a_date_missing_one_side_still_appears(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)
    await _create(
        client,
        headers,
        system_page_ids["daily_revenue"],
        "2026-09-05T20:00:00+05:30",
        {"entry_date": "2026-09-05", "cash_sales": "1000.00", "card_sales": "0.00"},
    )

    resp = await client.get("/reconciliation", headers=headers)
    assert resp.status_code == 200, resp.text
    item = next(i for i in resp.json()["items"] if i["business_date"] == "2026-09-05")
    assert item["revenue_total"] == "1000.00"
    assert item["ledger_total"] == "0.00"
    assert item["difference"] == "1000.00"


async def test_manager_without_both_grants_gets_404(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
    system_page_ids: dict[str, str],
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    # Grant only daily_revenue, not cash_ledger.
    await _grant(client, owner_headers, system_page_ids["daily_revenue"], manager)

    manager_headers = await _manager_headers(client, manager_password)
    resp = await client.get("/reconciliation", headers=manager_headers)
    assert resp.status_code == 404, resp.text


async def test_manager_with_both_grants_can_see_reconciliation(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
    system_page_ids: dict[str, str],
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    await _grant(client, owner_headers, system_page_ids["daily_revenue"], manager)
    await _grant(client, owner_headers, system_page_ids["cash_ledger"], manager)

    manager_headers = await _manager_headers(client, manager_password)
    resp = await client.get("/reconciliation", headers=manager_headers)
    assert resp.status_code == 200, resp.text
