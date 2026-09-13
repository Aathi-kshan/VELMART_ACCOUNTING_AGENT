"""Native-table behaviour that only a system page exercises (plan section
3.5.9): a DB `CHECK`/column constraint surfaces as a normal 422
`VALIDATION_FAILED` — the same shape a generic page's own validation would
give, not a raw database error — and the two DB-computed columns
(`daily_revenue.total_revenue`, `cash_ledger.total_amount`) recompute from
their inputs, are always present on read, and are never accepted on write.
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


async def test_negative_currency_amount_is_422(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = system_page_ids["expenses"]
    resp = await client.post(
        f"/pages/{page_id}/records",
        json={
            "occurred_at": "2026-09-01T10:00:00+05:30",
            "data": {"expense_date": "2026-09-01", "expense_name": "Rent", "amount": "-500.00"},
        },
        headers=headers,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == "VALIDATION_FAILED"


async def test_total_revenue_recomputes_and_is_readonly(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = system_page_ids["daily_revenue"]

    rejected = await client.post(
        f"/pages/{page_id}/records",
        json={
            "occurred_at": "2026-09-01T20:00:00+05:30",
            "data": {
                "entry_date": "2026-09-01",
                "cash_sales": "1.00",
                "card_sales": "1.00",
                "total_revenue": "999.00",
            },
        },
        headers=headers,
    )
    assert rejected.status_code == 422, rejected.text

    created = await client.post(
        f"/pages/{page_id}/records",
        json={
            "occurred_at": "2026-09-01T20:00:00+05:30",
            "data": {
                "entry_date": "2026-09-01",
                "cash_sales": "150000.00",
                "card_sales": "100000.00",
            },
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["data"]["total_revenue"] == "250000.00"

    fetched = await client.get(f"/records/{body['id']}", headers=headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["data"]["total_revenue"] == "250000.00"


async def test_total_amount_recomputes_on_cash_ledger(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = system_page_ids["cash_ledger"]
    resp = await client.post(
        f"/pages/{page_id}/records",
        json={
            "occurred_at": "2026-09-01T20:00:00+05:30",
            "data": {
                "entry_date": "2026-09-01",
                "cash_amount": "150000.00",
                "card_sales_amount": "98000.00",
            },
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["total_amount"] == "248000.00"


async def test_schema_exposes_generated_columns(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)

    revenue_schema = await client.get(
        f"/pages/{system_page_ids['daily_revenue']}/schema", headers=headers
    )
    assert revenue_schema.status_code == 200, revenue_schema.text
    assert revenue_schema.json()["generated_columns"] == ["total_revenue"]

    ledger_schema = await client.get(
        f"/pages/{system_page_ids['cash_ledger']}/schema", headers=headers
    )
    assert ledger_schema.status_code == 200, ledger_schema.text
    assert ledger_schema.json()["generated_columns"] == ["total_amount"]

    expenses_schema = await client.get(
        f"/pages/{system_page_ids['expenses']}/schema", headers=headers
    )
    assert expenses_schema.status_code == 200, expenses_schema.text
    assert expenses_schema.json()["generated_columns"] == []


async def test_generic_page_has_no_generated_columns(
    client: AsyncClient, owner: uuid.UUID, owner_password: str
) -> None:
    headers = await _owner_headers(client, owner_password)
    resp = await client.post(
        "/pages",
        json={"name": "Owner Table", "columns": [{"name": "Note", "data_type": "TEXT"}]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["generated_columns"] == []


async def test_editing_a_record_with_a_generated_column_does_not_422(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    """Regression test: `update_record` used to re-validate the merged
    old-data-plus-changes dict *including* the generated column's own
    stored value (e.g. `total_amount`), against a model that excludes
    generated columns as fields entirely — so every edit of a record on
    `cash_ledger`/`daily_revenue` 422'd with `extra_forbidden` on the
    generated column, even when the edit never touched it."""
    headers = await _owner_headers(client, owner_password)
    page_id = system_page_ids["cash_ledger"]
    created = await client.post(
        f"/pages/{page_id}/records",
        json={
            "occurred_at": "2026-09-01T20:00:00+05:30",
            "data": {
                "entry_date": "2026-09-01",
                "cash_amount": "100.00",
                "card_sales_amount": "50.00",
            },
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    record_id = created.json()["id"]
    assert created.json()["data"]["total_amount"] == "150.00"

    updated = await client.patch(
        f"/records/{record_id}",
        json={
            "version": 1,
            "data": {
                "entry_date": "2026-09-01",
                "cash_amount": "200.00",
                "card_sales_amount": "50.00",
            },
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["total_amount"] == "250.00"

    fetched = await client.get(f"/records/{record_id}", headers=headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["data"]["cash_amount"] == "200.00"
    assert fetched.json()["data"]["total_amount"] == "250.00"
