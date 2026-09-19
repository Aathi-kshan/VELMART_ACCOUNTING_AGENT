"""A page must not report two different totals for the same data.

A record's lifecycle `status` can be ACTIVE, VOID or REVERSED. Reversal
deliberately keeps the original row and writes a correcting record beside it
(`record_service.reverse_record`), so anything that produces a number has to
exclude non-ACTIVE rows or it counts the reversed entry twice — once as the
original and once as its replacement.

`running_balance` did that. `sum`, `avg`, `count` and `column-values` did
not, because they all started from `base_conditions`, which scopes by page
and `is_deleted` only. The result was a ledger page whose running balance
said one thing and whose total said another, with nothing to indicate which
was right. `test_ledger_pages.py::test_running_balance_excludes_a_reversed_record`
covered one half of that; this file covers the other half and, more
importantly, asserts the two agree.

Listing records deliberately still includes them: a reversed row stays
visible, carrying its status, rather than silently disappearing from the
table.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient


async def _owner_headers(client: AsyncClient, owner_password: str) -> dict[str, str]:
    resp = await client.post(
        "/auth/login",
        json={"email": "owner@test.lk", "password": owner_password, "device_id": "d1"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _ledger_page(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/pages",
        json={
            "name": f"Movements {uuid.uuid4().hex[:6]}",
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


async def _movement(
    client: AsyncClient, headers: dict[str, str], page_id: str, *, amount: str, note: str, at: str
) -> dict:
    resp = await client.post(
        f"/pages/{page_id}/records",
        json={"occurred_at": at, "data": {"amount": amount, "note": note}},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


async def _sum(client: AsyncClient, headers: dict[str, str], page_id: str) -> Decimal:
    resp = await client.post(
        f"/pages/{page_id}/aggregate",
        json={"metric": "sum", "column": "amount"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return Decimal(resp.json()["value"])


class TestReversedRowsAreExcludedFromNumbers:
    async def test_sum_excludes_a_reversed_record(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _ledger_page(client, headers)
        await _movement(
            client, headers, page_id, amount="100.00", note="a", at="2026-09-01T09:00:00+05:30"
        )
        middle = await _movement(
            client, headers, page_id, amount="50.00", note="b", at="2026-09-01T10:00:00+05:30"
        )
        await _movement(
            client, headers, page_id, amount="-30.00", note="c", at="2026-09-01T11:00:00+05:30"
        )
        assert await _sum(client, headers, page_id) == Decimal("120.00")

        reverse = await client.post(
            f"/records/{middle['id']}/reverse",
            json={"version": middle["version"]},
            headers=headers,
        )
        assert reverse.status_code == 200, reverse.text

        # The reversed 50.00 must drop out of the total.
        assert await _sum(client, headers, page_id) == Decimal("70.00")

    async def test_sum_and_running_balance_agree_after_a_reversal(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """The invariant that actually matters: a page's total and the last
        row of its running balance are the same number."""
        headers = await _owner_headers(client, owner_password)
        page_id = await _ledger_page(client, headers)
        await _movement(
            client, headers, page_id, amount="100.00", note="a", at="2026-09-01T09:00:00+05:30"
        )
        middle = await _movement(
            client, headers, page_id, amount="50.00", note="b", at="2026-09-01T10:00:00+05:30"
        )
        await _movement(
            client, headers, page_id, amount="-30.00", note="c", at="2026-09-01T11:00:00+05:30"
        )
        reverse = await client.post(
            f"/records/{middle['id']}/reverse",
            json={"version": middle["version"]},
            headers=headers,
        )
        assert reverse.status_code == 200, reverse.text

        balance = await client.get(f"/pages/{page_id}/running-balance", headers=headers)
        assert balance.status_code == 200, balance.text
        final_balance = Decimal(balance.json()["entries"][-1]["balance"])

        assert await _sum(client, headers, page_id) == final_balance

    async def test_a_replacement_record_is_counted(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """Excluding the original must not also exclude the correction."""
        headers = await _owner_headers(client, owner_password)
        page_id = await _ledger_page(client, headers)
        original = await _movement(
            client, headers, page_id, amount="50.00", note="typo", at="2026-09-01T09:00:00+05:30"
        )
        reverse = await client.post(
            f"/records/{original['id']}/reverse",
            json={"version": original["version"], "data": {"amount": "75.00", "note": "fixed"}},
            headers=headers,
        )
        assert reverse.status_code == 200, reverse.text

        # The 50.00 is reversed, the 75.00 replacement stands.
        assert await _sum(client, headers, page_id) == Decimal("75.00")

    async def test_count_excludes_reversed_rows_but_the_list_still_shows_them(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """Numbers exclude non-ACTIVE rows; the table does not. A reversed
        record staying visible with its status is the point of soft
        reversal."""
        headers = await _owner_headers(client, owner_password)
        page_id = await _ledger_page(client, headers)
        first = await _movement(
            client, headers, page_id, amount="10.00", note="a", at="2026-09-01T09:00:00+05:30"
        )
        await _movement(
            client, headers, page_id, amount="20.00", note="b", at="2026-09-01T10:00:00+05:30"
        )
        reverse = await client.post(
            f"/records/{first['id']}/reverse",
            json={"version": first["version"]},
            headers=headers,
        )
        assert reverse.status_code == 200, reverse.text

        counted = await client.post(
            f"/pages/{page_id}/aggregate", json={"metric": "count"}, headers=headers
        )
        assert counted.status_code == 200, counted.text
        assert counted.json()["value"] == "1"

        listed = await client.post(f"/pages/{page_id}/records/query", json={}, headers=headers)
        assert listed.status_code == 200, listed.text
        statuses = sorted(item["status"] for item in listed.json()["items"])
        assert statuses == ["ACTIVE", "REVERSED"], "a reversed record vanished from the list"

    async def test_column_values_does_not_offer_a_reversed_rows_value(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """`column-values` backs filter pickers, so offering a value that
        only a reversed row carries sends the user to an empty result."""
        headers = await _owner_headers(client, owner_password)
        page_id = await _ledger_page(client, headers)
        gone = await _movement(
            client,
            headers,
            page_id,
            amount="10.00",
            note="only-on-reversed",
            at="2026-09-01T09:00:00+05:30",
        )
        await _movement(
            client,
            headers,
            page_id,
            amount="20.00",
            note="still-here",
            at="2026-09-01T10:00:00+05:30",
        )
        reverse = await client.post(
            f"/records/{gone['id']}/reverse", json={"version": gone["version"]}, headers=headers
        )
        assert reverse.status_code == 200, reverse.text

        resp = await client.get(f"/pages/{page_id}/column-values/note", headers=headers)
        assert resp.status_code == 200, resp.text
        values = resp.json()["values"]
        assert "still-here" in values
        assert "only-on-reversed" not in values


class TestCountIsNotFormattedAsMoney:
    async def test_counting_a_currency_column_returns_a_row_count(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """`count` of a CURRENCY column is a number of rows, not an amount.
        It was being run through `format_money`, so 4 rows reported as
        "4.00"."""
        headers = await _owner_headers(client, owner_password)
        page_id = await _ledger_page(client, headers)
        for i in range(4):
            await _movement(
                client,
                headers,
                page_id,
                amount="10.00",
                note=f"n{i}",
                at=f"2026-09-01T0{i + 1}:00:00+05:30",
            )

        resp = await client.post(
            f"/pages/{page_id}/aggregate",
            json={"metric": "count", "column": "amount"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["value"] == "4", "a row count was formatted as money"
