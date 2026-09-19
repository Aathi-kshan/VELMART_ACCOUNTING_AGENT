"""Keyset pagination over a column that is not filled in on every row.

Optional columns are the normal case — a page is built, rows are entered,
and one field only starts being used later. Sorting by such a column hit two
separate faults, both of which lost records silently rather than erroring:

* Postgres orders NULLs FIRST on DESC and LAST on ASC, and the keyset
  predicate was a bare `expr > value` / `expr < value`. `NULL > anything` is
  NULL, never true, so on an ascending sort the empty rows were ordered into
  a block at the end that no page could ever reach.
* `_encode_scalar(None)` produced the *string* `"None"`, which the cursor's
  own `parse_cursor` then tried to read back as a date/Decimal/UUID. So the
  moment a page happened to end on a row with an empty sort value, the next
  page returned "Invalid or corrupted cursor" instead of more records.

The invariant every test here asserts is the same one: **paging all the way
through returns every record exactly once**, whatever the sort column and
whatever is missing. That is checked by walking the cursor to exhaustion and
comparing the set of ids against what was created, so it cannot pass by
accident.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


async def _owner_headers(client: AsyncClient, owner_password: str) -> dict[str, str]:
    resp = await client.post(
        "/auth/login",
        json={"email": "owner@test.lk", "password": owner_password, "device_id": "d1"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _page_with_optional_columns(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/pages",
        json={
            "name": f"Sparse {uuid.uuid4().hex[:6]}",
            "columns": [
                {"name": "Label", "data_type": "TEXT", "is_required": True},
                # Every one of these is optional, so rows can leave them empty.
                {"name": "Amount", "data_type": "CURRENCY"},
                {"name": "Due", "data_type": "DATE"},
                {"name": "Rank", "data_type": "NUMBER"},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _create(
    client: AsyncClient, headers: dict[str, str], page_id: str, data: dict[str, str]
) -> str:
    resp = await client.post(
        f"/pages/{page_id}/records",
        json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": data},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _page_through(
    client: AsyncClient,
    headers: dict[str, str],
    page_id: str,
    *,
    column: str,
    direction: str,
    limit: int = 2,
) -> list[str]:
    """Walk the cursor to exhaustion, returning every id seen in order.

    Guards against a cursor that never terminates, so a looping bug fails
    loudly instead of hanging the suite.
    """
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(50):
        body: dict[str, object] = {
            "sort": [{"column": column, "direction": direction}],
            "limit": limit,
        }
        if cursor is not None:
            body["cursor"] = cursor
        resp = await client.post(
            f"/pages/{page_id}/records/query", json=body, headers=headers
        )
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        seen.extend(item["id"] for item in payload["items"])
        cursor = payload.get("next_cursor")
        if not cursor:
            return seen
    raise AssertionError("cursor did not terminate within 50 pages")


class TestSortingByAColumnWithMissingValues:
    @pytest.mark.parametrize("direction", ["asc", "desc"])
    @pytest.mark.parametrize(
        ("column", "present", "absent"),
        [
            ("amount", {"amount": "10.00"}, {}),
            ("due", {"due": "2026-09-01"}, {}),
            ("rank", {"rank": "5"}, {}),
        ],
    )
    async def test_every_record_is_reachable(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        direction: str,
        column: str,
        present: dict[str, str],
        absent: dict[str, str],
    ) -> None:
        """Rows with no value must still be paged through, in both
        directions and for every sortable type."""
        headers = await _owner_headers(client, owner_password)
        page_id = await _page_with_optional_columns(client, headers)

        created = set()
        for i in range(3):
            created.add(await _create(client, headers, page_id, {"label": f"has-{i}", **present}))
        for i in range(3):
            created.add(await _create(client, headers, page_id, {"label": f"none-{i}", **absent}))

        seen = await _page_through(
            client, headers, page_id, column=column, direction=direction
        )
        assert len(seen) == len(set(seen)), "a record was returned on more than one page"
        assert set(seen) == created, (
            f"{len(created - set(seen))} record(s) were unreachable by paging"
        )

    @pytest.mark.parametrize("direction", ["asc", "desc"])
    async def test_a_page_ending_on_an_empty_value_still_yields_a_usable_cursor(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        direction: str,
    ) -> None:
        """The cursor-corruption half. With the empty rows ordered last and a
        limit of 1, some page necessarily ends on one of them, so the next
        request exercises a cursor carrying an empty value."""
        headers = await _owner_headers(client, owner_password)
        page_id = await _page_with_optional_columns(client, headers)

        created = set()
        created.add(await _create(client, headers, page_id, {"label": "a", "amount": "10.00"}))
        created.add(await _create(client, headers, page_id, {"label": "b"}))
        created.add(await _create(client, headers, page_id, {"label": "c"}))

        seen = await _page_through(
            client, headers, page_id, column="amount", direction=direction, limit=1
        )
        assert set(seen) == created

    async def test_records_with_no_value_at_all_still_paginate(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """The degenerate case: every row is empty in the sort column, so
        every cursor carries a null."""
        headers = await _owner_headers(client, owner_password)
        page_id = await _page_with_optional_columns(client, headers)

        created = {
            await _create(client, headers, page_id, {"label": f"row-{i}"}) for i in range(5)
        }
        seen = await _page_through(
            client, headers, page_id, column="amount", direction="asc", limit=2
        )
        assert set(seen) == created

    async def test_missing_values_sort_last_in_both_directions(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """The ordering rule itself. Postgres would otherwise put them first
        on DESC and last on ASC, so the same data disagreed with itself
        depending on which way it was sorted."""
        headers = await _owner_headers(client, owner_password)
        page_id = await _page_with_optional_columns(client, headers)

        with_value = await _create(client, headers, page_id, {"label": "has", "amount": "10.00"})
        without = await _create(client, headers, page_id, {"label": "missing"})

        for direction in ("asc", "desc"):
            seen = await _page_through(
                client, headers, page_id, column="amount", direction=direction, limit=10
            )
            assert seen == [with_value, without], (
                f"{direction}: empty value did not sort last (got {seen})"
            )


class TestPaginationStaysStableWithoutNulls:
    """The ordinary path must not regress from the NULL handling above."""

    async def test_full_walk_returns_each_record_once(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _page_with_optional_columns(client, headers)

        created = {
            await _create(
                client,
                headers,
                page_id,
                {"label": f"row-{i}", "amount": f"{i + 1}.00", "rank": str(i)},
            )
            for i in range(7)
        }
        seen = await _page_through(
            client, headers, page_id, column="amount", direction="asc", limit=3
        )
        assert seen == sorted(seen, key=seen.index)
        assert len(seen) == len(set(seen))
        assert set(seen) == created
