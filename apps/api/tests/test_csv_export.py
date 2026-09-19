"""`POST /pages/{page_id}/export` (plan section 13.2, P3.5 Part 2) — one
generic CSV export pipeline for any page, owner only. Delivers the file
directly in the response body (a deliberate deviation from the locked
spec's presigned-bucket-URL design — see `app/services/csv_service.py`'s
module docstring), so the assertions here are about content, not a URL.
"""

from __future__ import annotations

import csv
import io
import uuid

from httpx import AsyncClient
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


async def _create_page(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/pages",
        json={
            "name": "Outgoings Export",
            "columns": [
                {"name": "Category", "data_type": "TEXT", "is_required": True},
                {"name": "Amount", "data_type": "CURRENCY", "is_required": True},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _create_record(
    client: AsyncClient, headers: dict[str, str], page_id: str, category: str, amount: str
) -> None:
    resp = await client.post(
        f"/pages/{page_id}/records",
        json={
            "occurred_at": "2026-09-01T10:00:00+05:30",
            "data": {"category": category, "amount": amount},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


def _parse_csv(body: bytes) -> list[list[str]]:
    text = body.decode("utf-8-sig")  # strips the BOM if present
    return list(csv.reader(io.StringIO(text)))


async def test_export_has_bom_header_and_rows(
    client: AsyncClient, owner: uuid.UUID, owner_password: str
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = await _create_page(client, headers)
    await _create_record(client, headers, page_id, "Electricity", "3500.00")
    await _create_record(client, headers, page_id, "Rent", "50000.00")

    resp = await client.post(f"/pages/{page_id}/export", json={}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.content.startswith(b"\xef\xbb\xbf")

    rows = _parse_csv(resp.content)
    assert rows[0] == ["Business Date", "Category", "Amount"]
    data_rows = rows[1:]
    assert len(data_rows) == 2
    assert {row[1] for row in data_rows} == {"Electricity", "Rent"}


async def test_export_respects_filters(
    client: AsyncClient, owner: uuid.UUID, owner_password: str
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = await _create_page(client, headers)
    await _create_record(client, headers, page_id, "Electricity", "3500.00")
    await _create_record(client, headers, page_id, "Rent", "50000.00")

    resp = await client.post(
        f"/pages/{page_id}/export",
        json={"filters": [{"column": "amount", "op": "gte", "value": "10000.00"}]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    rows = _parse_csv(resp.content)
    data_rows = rows[1:]
    assert len(data_rows) == 1
    assert data_rows[0][1] == "Rent"


async def test_manager_cannot_export(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    page_id = await _create_page(client, owner_headers)

    manager_headers = await _manager_headers(client, manager_password)
    resp = await client.post(f"/pages/{page_id}/export", json={}, headers=manager_headers)
    assert resp.status_code == 403, resp.text


async def test_export_writes_an_audit_entry(
    client: AsyncClient, owner: uuid.UUID, owner_password: str, session: AsyncSession
) -> None:
    from sqlalchemy import text

    headers = await _owner_headers(client, owner_password)
    page_id = await _create_page(client, headers)
    await _create_record(client, headers, page_id, "Electricity", "3500.00")

    resp = await client.post(f"/pages/{page_id}/export", json={}, headers=headers)
    assert resp.status_code == 200, resp.text

    row = (
        await session.execute(
            text(
                "SELECT new_data FROM audit_logs "
                "WHERE action = 'CSV_EXPORT' AND entity_id = :page_id"
            ),
            {"page_id": page_id},
        )
    ).one()
    assert row.new_data["row_count"] == 1


async def test_export_works_for_a_system_page(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)

    # This isn't about identical *schemas* — it's about the export pipeline
    # behaving identically over the native-table storage backend: a BOM, a
    # header row matching column names in position order, one row per record.
    resp = await client.post(
        f"/pages/{system_page_ids['expenses']}/export", json={}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.content.startswith(b"\xef\xbb\xbf")

    create = await client.post(
        f"/pages/{system_page_ids['expenses']}/records",
        json={
            "occurred_at": "2026-09-01T10:00:00+05:30",
            "data": {"expense_date": "2026-09-01", "expense_name": "Water", "amount": "1200.00"},
        },
        headers=headers,
    )
    assert create.status_code == 201, create.text

    resp = await client.post(
        f"/pages/{system_page_ids['expenses']}/export", json={}, headers=headers
    )
    rows = _parse_csv(resp.content)
    # Business Date, Expense Date, Entry Time, Expense Name, Amount, Description
    # (column order mirrors page_service's registered position order).
    assert rows[0] == [
        "Business Date",
        "Expense Date",
        "Entry Time",
        "Expense Name",
        "Amount",
        "Description",
    ]
    assert "Water" in {row[3] for row in rows[1:]}
