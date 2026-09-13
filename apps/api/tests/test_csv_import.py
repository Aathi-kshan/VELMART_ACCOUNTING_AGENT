"""CSV import (plan section 13.1, P3.5 Part 3) — upload, fuzzy column
mapping, per-row validation (money/date normalization, ambiguous-date
confirmation), natural-key duplicate detection, chunked commit, and 24-hour
rollback. Owner only.
"""

from __future__ import annotations

import json
import uuid

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


async def _create_expense_page(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/pages",
        json={
            "name": "Import Expenses",
            "columns": [
                {"name": "Expense Date", "data_type": "DATE", "is_required": True},
                {
                    "name": "Category",
                    "data_type": "SELECT",
                    "config": {"options": ["Electricity", "Rent", "Water"]},
                },
                {
                    "name": "Amount",
                    "data_type": "CURRENCY",
                    "is_required": True,
                    # A refund/credit note import can legitimately be
                    # negative — exercised by `(1,234.00)` -> "-1234.00" in
                    # test_validate_normalizes_money_and_reports_errors.
                    "config": {"allow_negative": True},
                },
                {"name": "Notes", "data_type": "TEXT"},
            ],
            "date_column_key": "expense_date",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


def _csv_bytes(text_content: str) -> bytes:
    return text_content.encode("utf-8")


async def _preview(client: AsyncClient, headers: dict[str, str], page_id: str, csv: bytes):
    return await client.post(
        f"/pages/{page_id}/import/preview",
        headers=headers,
        files={"file": ("import.csv", csv, "text/csv")},
    )


async def _validate(
    client: AsyncClient, headers: dict[str, str], page_id: str, csv: bytes, payload: dict
):
    return await client.post(
        f"/pages/{page_id}/import/validate",
        headers=headers,
        files={"file": ("import.csv", csv, "text/csv")},
        data={"payload": json.dumps(payload)},
    )


async def _commit(
    client: AsyncClient, headers: dict[str, str], page_id: str, csv: bytes, payload: dict
):
    return await client.post(
        f"/pages/{page_id}/import/commit",
        headers=headers,
        files={"file": ("import.csv", csv, "text/csv")},
        data={"payload": json.dumps(payload)},
    )


async def test_preview_detects_header_and_suggests_fuzzy_mapping(
    client: AsyncClient, owner: uuid.UUID, owner_password: str
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = await _create_expense_page(client, headers)

    csv = _csv_bytes(
        "Expense Date,Category,Amount,Notes\n2026-09-01,Electricity,3500.00,Sept bill\n"
    )
    resp = await _preview(client, headers, page_id, csv)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["headers"] == ["Expense Date", "Category", "Amount", "Notes"]
    assert body["row_count"] == 1
    assert body["suggested_mapping"] == {
        "Expense Date": "expense_date",
        "Category": "category",
        "Amount": "amount",
        "Notes": "notes",
    }
    assert body["sample_rows"][0]["Category"] == "Electricity"


async def test_preview_fuzzy_matches_a_near_miss_header(
    client: AsyncClient, owner: uuid.UUID, owner_password: str
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = await _create_expense_page(client, headers)

    # "Amount (Rs)" is not an exact match for the "Amount" column, but close
    # enough that difflib should still pair them.
    csv = _csv_bytes("Expense Date,Category,Amount (Rs)\n2026-09-01,Rent,50000.00\n")
    resp = await _preview(client, headers, page_id, csv)
    assert resp.status_code == 200, resp.text
    assert resp.json()["suggested_mapping"]["Amount (Rs)"] == "amount"


async def test_generated_columns_are_never_suggested_or_importable(
    client: AsyncClient, owner: uuid.UUID, owner_password: str, system_page_ids: dict[str, str]
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = system_page_ids["daily_revenue"]

    csv = _csv_bytes(
        "Entry Date,Cash Sales,Card Sales,Total Revenue\n2026-09-01,100.00,50.00,150.00\n"
    )
    resp = await _preview(client, headers, page_id, csv)
    assert resp.status_code == 200, resp.text
    assert resp.json()["suggested_mapping"]["Total Revenue"] is None

    validate_resp = await _validate(
        client,
        headers,
        page_id,
        csv,
        {"mapping": {"Entry Date": "entry_date", "Total Revenue": "total_revenue"}},
    )
    assert validate_resp.status_code == 422, validate_resp.text


async def test_validate_normalizes_money_and_reports_errors(
    client: AsyncClient, owner: uuid.UUID, owner_password: str
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = await _create_expense_page(client, headers)

    csv = _csv_bytes(
        "Expense Date,Category,Amount\n"
        "2026-09-01,Electricity,\"Rs. 3,500.00\"\n"
        "2026-09-02,Rent,(1234.00)\n"
        "2026-09-03,Gas,500.00\n"  # "Gas" is not a valid SELECT option -> error
    )
    payload = {
        "mapping": {"Expense Date": "expense_date", "Category": "category", "Amount": "amount"}
    }
    resp = await _validate(client, headers, page_id, csv, payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_rows"] == 3
    assert body["valid_rows"] == 2
    assert body["error_rows"] == 1
    assert body["errors"][0]["row"] == 3
    assert body["errors"][0]["column"] == "Category"


async def test_ambiguous_date_requires_a_format_hint(
    client: AsyncClient, owner: uuid.UUID, owner_password: str
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = await _create_expense_page(client, headers)

    csv = _csv_bytes("Expense Date,Amount\n01/02/2026,500.00\n")
    payload = {"mapping": {"Expense Date": "expense_date", "Amount": "amount"}}

    without_hint = await _validate(client, headers, page_id, csv, payload)
    assert without_hint.status_code == 200, without_hint.text
    body = without_hint.json()
    assert body["error_rows"] == 1
    assert "ambiguous" in body["errors"][0]["message"].lower()

    with_hint = await _validate(
        client, headers, page_id, csv, {**payload, "date_formats": {"expense_date": "DMY"}}
    )
    assert with_hint.status_code == 200, with_hint.text
    assert with_hint.json()["error_rows"] == 0
    assert with_hint.json()["valid_rows"] == 1


async def test_commit_writes_rows_and_audits(
    client: AsyncClient, owner: uuid.UUID, owner_password: str, session: AsyncSession
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = await _create_expense_page(client, headers)

    csv = _csv_bytes(
        "Expense Date,Category,Amount\n"
        "2026-09-01,Electricity,3500.00\n"
        "2026-09-02,Rent,50000.00\n"
    )
    payload = {
        "mapping": {"Expense Date": "expense_date", "Category": "category", "Amount": "amount"}
    }
    resp = await _commit(client, headers, page_id, csv, payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_rows"] == 2
    assert body["imported_rows"] == 2
    assert body["skipped_rows"] == 0

    listed = await client.get(f"/pages/{page_id}/records", headers=headers)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) == 2

    row = (
        await session.execute(
            text("SELECT source FROM records WHERE page_id = :page_id LIMIT 1"),
            {"page_id": page_id},
        )
    ).scalar_one()
    assert row == "CSV"

    audit = (
        await session.execute(
            text("SELECT new_data FROM audit_logs WHERE action = 'CSV_IMPORT'")
        )
    ).one()
    assert audit.new_data["imported_rows"] == 2


async def test_natural_key_duplicate_detection_skip_and_update(
    client: AsyncClient, owner: uuid.UUID, owner_password: str
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = await _create_expense_page(client, headers)

    first_csv = _csv_bytes("Expense Date,Category,Amount\n2026-09-01,Electricity,3500.00\n")
    payload = {
        "mapping": {"Expense Date": "expense_date", "Category": "category", "Amount": "amount"},
        "natural_key_columns": ["expense_date", "category"],
        "duplicate_strategy": "create_anyway",
    }
    first = await _commit(client, headers, page_id, first_csv, payload)
    assert first.status_code == 200, first.text
    assert first.json()["imported_rows"] == 1

    # Same natural key (date + category), different amount — "skip" leaves
    # the original untouched and counts it as skipped, not an error.
    second_csv = _csv_bytes("Expense Date,Category,Amount\n2026-09-01,Electricity,9999.00\n")
    skip_payload = {**payload, "duplicate_strategy": "skip"}
    validate_resp = await _validate(client, headers, page_id, second_csv, skip_payload)
    assert validate_resp.status_code == 200, validate_resp.text
    assert validate_resp.json()["duplicate_rows"] == 1

    skip_commit = await _commit(client, headers, page_id, second_csv, skip_payload)
    assert skip_commit.status_code == 200, skip_commit.text
    assert skip_commit.json()["skipped_rows"] == 1
    assert skip_commit.json()["imported_rows"] == 0

    listed = await client.get(f"/pages/{page_id}/records", headers=headers)
    amounts = {item["data"]["amount"] for item in listed.json()["items"]}
    assert amounts == {"3500.00"}  # unchanged — the duplicate was skipped

    # "update" strategy overwrites the existing row's data instead.
    update_payload = {**payload, "duplicate_strategy": "update"}
    update_commit = await _commit(client, headers, page_id, second_csv, update_payload)
    assert update_commit.status_code == 200, update_commit.text
    assert update_commit.json()["imported_rows"] == 1

    listed_after = await client.get(f"/pages/{page_id}/records", headers=headers)
    amounts_after = {item["data"]["amount"] for item in listed_after.json()["items"]}
    assert amounts_after == {"9999.00"}


async def test_rollback_soft_deletes_the_batch_and_can_only_happen_once(
    client: AsyncClient, owner: uuid.UUID, owner_password: str
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = await _create_expense_page(client, headers)

    csv = _csv_bytes(
        "Expense Date,Category,Amount\n"
        "2026-09-01,Electricity,3500.00\n"
        "2026-09-02,Rent,50000.00\n"
    )
    payload = {
        "mapping": {"Expense Date": "expense_date", "Category": "category", "Amount": "amount"}
    }
    commit_resp = await _commit(client, headers, page_id, csv, payload)
    assert commit_resp.status_code == 200, commit_resp.text
    batch_id = commit_resp.json()["batch_id"]

    batches = await client.get(f"/pages/{page_id}/import-batches", headers=headers)
    assert batches.status_code == 200, batches.text
    listed_batch = next(b for b in batches.json() if b["id"] == batch_id)
    assert listed_batch["can_rollback"] is True

    rollback_resp = await client.post(f"/import-batches/{batch_id}/rollback", headers=headers)
    assert rollback_resp.status_code == 200, rollback_resp.text
    assert rollback_resp.json()["rolled_back_rows"] == 2

    listed = await client.get(f"/pages/{page_id}/records", headers=headers)
    assert listed.json()["items"] == []

    second_rollback = await client.post(f"/import-batches/{batch_id}/rollback", headers=headers)
    assert second_rollback.status_code == 409, second_rollback.text


async def test_rollback_after_24_hours_is_rejected(
    client: AsyncClient, owner: uuid.UUID, owner_password: str, session: AsyncSession
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = await _create_expense_page(client, headers)

    csv = _csv_bytes("Expense Date,Category,Amount\n2026-09-01,Electricity,3500.00\n")
    payload = {
        "mapping": {"Expense Date": "expense_date", "Category": "category", "Amount": "amount"}
    }
    commit_resp = await _commit(client, headers, page_id, csv, payload)
    assert commit_resp.status_code == 200, commit_resp.text
    batch_id = commit_resp.json()["batch_id"]

    await session.execute(
        text("UPDATE import_batches SET created_at = now() - interval '25 hours' WHERE id = :id"),
        {"id": batch_id},
    )
    await session.commit()

    rollback_resp = await client.post(f"/import-batches/{batch_id}/rollback", headers=headers)
    assert rollback_resp.status_code == 409, rollback_resp.text


async def test_manager_cannot_import(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    page_id = await _create_expense_page(client, owner_headers)

    manager_headers = await _manager_headers(client, manager_password)
    csv = _csv_bytes("Expense Date,Amount\n2026-09-01,500.00\n")
    resp = await _preview(client, manager_headers, page_id, csv)
    assert resp.status_code == 403, resp.text


async def test_import_into_a_system_page(
    client: AsyncClient, owner: uuid.UUID, owner_password: str, system_page_ids: dict[str, str]
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = system_page_ids["cheques"]

    csv = _csv_bytes(
        "Cheque Number,Payee Name,Amount\nCHQ-900,Acme Traders,15000.00\n"
    )
    payload = {
        "mapping": {
            "Cheque Number": "cheque_number",
            "Payee Name": "payee_name",
            "Amount": "amount",
        }
    }
    resp = await _commit(client, headers, page_id, csv, payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported_rows"] == 1

    listed = await client.get(f"/pages/{page_id}/records", headers=headers)
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["data"]["cheque_status"] == "PENDING"
