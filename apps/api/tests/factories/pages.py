"""Two differently-structured fixture companies (plan section 16.10, P7.13)
— the raw material for the golden-question evaluation (Slice 14).

Every page and record goes through the public API (`POST /pages`,
`POST /pages/{id}/records`), never a direct row insert — proof that a
golden question's answer comes from the same schema-discovery path the AI
itself uses, not from data shaped to match some internal assumption.
Company/Owner creation has no public signup endpoint in this system (an
out-of-band ops step by design — see the existing `company`/`owner`
fixtures in `tests/conftest.py`), so a caller supplies an authenticated
`client`/`headers` pair already pointed at one.

Fixture A ("Vehicle Costs") and Fixture B ("Operational Outlay") describe
the same kind of business fact — vehicle-related running costs — with
deliberately different page names, column names, column order, and column
types. If an AI tool or prompt ever hardcoded a real business's shape,
answering the same question against both fixtures would expose it.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

#: (occurred_at, data) rows for each of the six shipped system pages —
#: shared by both fixtures, since every company ships with these regardless
#: of whatever else the Owner has built.
_SYSTEM_PAGE_ROWS: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "employee_salary": [
        (
            "2026-01-05T09:00:00Z",
            {
                "payment_date": "2026-01-05",
                "employee_name": "Kasun Perera",
                "paid_amount": "45000.00",
            },
        ),
        (
            "2026-01-05T09:05:00Z",
            {
                "payment_date": "2026-01-05",
                "employee_name": "Nimal Silva",
                "paid_amount": "42000.00",
            },
        ),
    ],
    "purchases": [
        (
            "2026-01-03T09:00:00Z",
            {
                "purchase_date": "2026-01-03",
                "purchase_name": "Rice - 50kg bags",
                "total_amount": "18000.00",
            },
        ),
        (
            "2026-01-12T09:00:00Z",
            {
                "purchase_date": "2026-01-12",
                "purchase_name": "Cooking oil",
                "total_amount": "9500.00",
            },
        ),
    ],
    "expenses": [
        (
            "2026-01-04T09:00:00Z",
            {"expense_date": "2026-01-04", "expense_name": "Electricity", "amount": "12500.00"},
        ),
        (
            "2026-01-18T09:00:00Z",
            {"expense_date": "2026-01-18", "expense_name": "Electricity", "amount": "13100.00"},
        ),
        (
            "2026-01-07T09:00:00Z",
            {"expense_date": "2026-01-07", "expense_name": "Water", "amount": "3200.00"},
        ),
    ],
    "daily_revenue": [
        (
            "2026-01-05T20:00:00Z",
            {"entry_date": "2026-01-05", "cash_sales": "85000.00", "card_sales": "32000.00"},
        ),
        (
            "2026-01-06T20:00:00Z",
            {"entry_date": "2026-01-06", "cash_sales": "91000.00", "card_sales": "28000.00"},
        ),
    ],
    "cash_ledger": [
        (
            "2026-01-05T20:30:00Z",
            {
                "entry_date": "2026-01-05",
                "cash_amount": "85000.00",
                "card_sales_amount": "32000.00",
            },
        ),
    ],
    "cheques": [
        (
            "2026-01-10T09:00:00Z",
            {
                "cheque_number": "CHQ-1001",
                "payee_name": "ABC Distributors",
                "amount": "25000.00",
                "cheque_date": "2026-01-10",
            },
        ),
    ],
}

FIXTURE_A_PAGE: dict[str, Any] = {
    "name": "Vehicle Costs",
    "columns": [
        {"name": "Vehicle", "data_type": "TEXT"},
        {"name": "Litres", "data_type": "NUMBER"},
        {"name": "Cost", "data_type": "CURRENCY"},
        {
            "name": "Category",
            "data_type": "SELECT",
            "config": {"options": ["Fuel", "Repair", "Insurance"]},
        },
    ],
    "rows": [
        (
            "2026-01-05T09:00:00Z",
            {"vehicle": "Van 1", "litres": "40", "cost": "12000.00", "category": "Fuel"},
        ),
        (
            "2026-01-10T09:00:00Z",
            {"vehicle": "Van 2", "litres": "35", "cost": "10500.00", "category": "Fuel"},
        ),
        (
            "2026-01-15T09:00:00Z",
            {"vehicle": "Van 1", "litres": "0", "cost": "5000.00", "category": "Repair"},
        ),
    ],
}

#: Same kind of fact as Fixture A (vehicle-related running costs), but a
#: different name, different column names, different column order
#: (department/select comes first here, not last), and a Qty/Amount split
#: instead of Litres/Cost.
FIXTURE_B_PAGE: dict[str, Any] = {
    "name": "Operational Outlay",
    "columns": [
        {
            "name": "Department",
            "data_type": "SELECT",
            "config": {"options": ["Vehicles", "Utilities", "Admin"]},
        },
        {"name": "Item", "data_type": "TEXT"},
        {"name": "Qty", "data_type": "NUMBER"},
        {"name": "Amount", "data_type": "CURRENCY"},
    ],
    "rows": [
        (
            "2026-01-06T09:00:00Z",
            {"department": "Vehicles", "item": "Diesel top-up", "qty": "38", "amount": "11400.00"},
        ),
        (
            "2026-01-11T09:00:00Z",
            {"department": "Utilities", "item": "Generator fuel", "qty": "20", "amount": "6000.00"},
        ),
        (
            "2026-01-20T09:00:00Z",
            {"department": "Vehicles", "item": "Brake pads", "qty": "1", "amount": "4500.00"},
        ),
    ],
}


async def _create_record(
    client: AsyncClient,
    headers: dict[str, str],
    page_id: str,
    *,
    occurred_at: str,
    data: dict[str, Any],
) -> None:
    resp = await client.post(
        f"/pages/{page_id}/records",
        json={"occurred_at": occurred_at, "data": data},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


async def seed_system_page_rows(
    client: AsyncClient, headers: dict[str, str], system_page_ids: dict[str, str]
) -> None:
    """A handful of realistic rows on each of the six shipped system pages,
    entirely through the public API — the same rows both fixtures share."""
    for key, rows in _SYSTEM_PAGE_ROWS.items():
        page_id = system_page_ids[key]
        for occurred_at, data in rows:
            await _create_record(client, headers, page_id, occurred_at=occurred_at, data=data)


async def _build_fixture(
    client: AsyncClient,
    headers: dict[str, str],
    page_def: dict[str, Any],
    system_page_ids: dict[str, str],
) -> dict[str, Any]:
    resp = await client.post(
        "/pages",
        json={"name": page_def["name"], "columns": page_def["columns"]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    page = resp.json()

    for occurred_at, data in page_def["rows"]:
        await _create_record(client, headers, page["id"], occurred_at=occurred_at, data=data)

    await seed_system_page_rows(client, headers, system_page_ids)
    return page


async def build_fixture_a(
    client: AsyncClient, headers: dict[str, str], system_page_ids: dict[str, str]
) -> dict[str, Any]:
    """ "Vehicle Costs" plus the six system pages, all through the public API."""
    return await _build_fixture(client, headers, FIXTURE_A_PAGE, system_page_ids)


async def build_fixture_b(
    client: AsyncClient, headers: dict[str, str], system_page_ids: dict[str, str]
) -> dict[str, Any]:
    """ "Operational Outlay" (structurally different from Fixture A) plus
    the six system pages, all through the public API."""
    return await _build_fixture(client, headers, FIXTURE_B_PAGE, system_page_ids)
