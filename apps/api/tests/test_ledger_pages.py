"""Ledger pages, reversal, and running balance (plan section 11.5, P4 §8;
docs/PROJECT_PLAN.md §4.4's `ACTIVE -> REVERSED` state machine). Scoped to
Owner-created `kind=LEDGER` generic pages only — no system page is
documented as ledger-style, and `BusinessTableMixin` has no
`reverses_id`-equivalent column (see `record_service.reverse_record`'s own
docstring).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

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


async def _create_ledger_page(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/pages",
        json={
            "name": "Cash Movements",
            "kind": "LEDGER",
            "columns": [
                {
                    "name": "Amount",
                    "data_type": "CURRENCY",
                    "is_required": True,
                    "config": {"allow_negative": True},
                },
                {"name": "Note", "data_type": "TEXT"},
            ],
            "balance_column_key": "amount",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _create_movement(
    client: AsyncClient, headers: dict[str, str], page_id: str, *, amount: str, occurred_at: str
) -> dict:
    resp = await client.post(
        f"/pages/{page_id}/records",
        json={"occurred_at": occurred_at, "data": {"amount": amount, "note": "x"}},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestLedgerImmutability:
    async def test_patch_on_a_ledger_records_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_ledger_page(client, headers)
        record = await _create_movement(
            client, headers, page_id, amount="100.00", occurred_at="2026-09-01T10:00:00+05:30"
        )

        resp = await client.patch(
            f"/records/{record['id']}",
            json={"version": record["version"], "data": {"amount": "200.00"}},
            headers=headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "LEDGER_RECORD_IMMUTABLE"


class TestReversal:
    async def test_reverse_flips_original_and_creates_linked_replacement(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_ledger_page(client, headers)
        record = await _create_movement(
            client, headers, page_id, amount="100.00", occurred_at="2026-09-01T10:00:00+05:30"
        )

        resp = await client.post(
            f"/records/{record['id']}/reverse",
            json={"version": record["version"], "data": {"amount": "90.00", "note": "corrected"}},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["original"]["status"] == "REVERSED"
        assert body["replacement"] is not None
        assert body["replacement"]["reverses_id"] == record["id"]
        assert body["replacement"]["data"]["amount"] == "90.00"
        assert body["replacement"]["status"] == "ACTIVE"

    async def test_reverse_without_replacement_data_leaves_no_new_record(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_ledger_page(client, headers)
        record = await _create_movement(
            client, headers, page_id, amount="100.00", occurred_at="2026-09-01T10:00:00+05:30"
        )

        resp = await client.post(
            f"/records/{record['id']}/reverse",
            json={"version": record["version"]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["original"]["status"] == "REVERSED"
        assert body["replacement"] is None

        listing = await client.post(
            f"/pages/{page_id}/records/query", json={}, headers=headers
        )
        assert len(listing.json()["items"]) == 1

    async def test_reversing_an_already_reversed_record_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_ledger_page(client, headers)
        record = await _create_movement(
            client, headers, page_id, amount="100.00", occurred_at="2026-09-01T10:00:00+05:30"
        )
        first = await client.post(
            f"/records/{record['id']}/reverse",
            json={"version": record["version"]},
            headers=headers,
        )
        assert first.status_code == 200, first.text

        second = await client.post(
            f"/records/{record['id']}/reverse",
            json={"version": first.json()["original"]["version"]},
            headers=headers,
        )
        assert second.status_code == 422, second.text

    async def test_reverse_on_a_register_page_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        resp = await client.post(
            "/pages",
            json={
                "name": "Ordinary Page",
                "columns": [{"name": "Amount", "data_type": "CURRENCY", "is_required": True}],
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        page_id = resp.json()["id"]
        record = await client.post(
            f"/pages/{page_id}/records",
            json={
                "occurred_at": "2026-09-01T10:00:00+05:30",
                "data": {"amount": "10.00"},
            },
            headers=headers,
        )
        assert record.status_code == 201, record.text
        body = record.json()

        resp = await client.post(
            f"/records/{body['id']}/reverse",
            json={"version": body["version"]},
            headers=headers,
        )
        assert resp.status_code == 422, resp.text


class TestRunningBalance:
    async def test_running_balance_matches_a_hand_computed_cumulative_sum(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_ledger_page(client, headers)
        await _create_movement(
            client, headers, page_id, amount="100.00", occurred_at="2026-09-01T09:00:00+05:30"
        )
        await _create_movement(
            client, headers, page_id, amount="50.00", occurred_at="2026-09-01T10:00:00+05:30"
        )
        await _create_movement(
            client, headers, page_id, amount="-30.00", occurred_at="2026-09-01T11:00:00+05:30"
        )

        resp = await client.get(f"/pages/{page_id}/running-balance", headers=headers)
        assert resp.status_code == 200, resp.text
        entries = resp.json()["entries"]
        balances = [Decimal(e["balance"]) for e in entries]
        assert balances == [Decimal("100.00"), Decimal("150.00"), Decimal("120.00")]

    async def test_running_balance_excludes_a_reversed_record(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_ledger_page(client, headers)
        await _create_movement(
            client, headers, page_id, amount="100.00", occurred_at="2026-09-01T09:00:00+05:30"
        )
        middle = await _create_movement(
            client, headers, page_id, amount="50.00", occurred_at="2026-09-01T10:00:00+05:30"
        )
        await _create_movement(
            client, headers, page_id, amount="-30.00", occurred_at="2026-09-01T11:00:00+05:30"
        )

        reverse = await client.post(
            f"/records/{middle['id']}/reverse",
            json={"version": middle["version"]},
            headers=headers,
        )
        assert reverse.status_code == 200, reverse.text

        resp = await client.get(f"/pages/{page_id}/running-balance", headers=headers)
        assert resp.status_code == 200, resp.text
        entries = resp.json()["entries"]
        assert len(entries) == 2
        balances = [Decimal(e["balance"]) for e in entries]
        assert balances == [Decimal("100.00"), Decimal("70.00")]
