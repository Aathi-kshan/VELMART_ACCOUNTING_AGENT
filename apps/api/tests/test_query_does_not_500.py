"""Ordinary input must never produce a 500.

Two paths in `query_service`/`records.resolve_column` raised a raw Postgres
error rather than a 4xx, and both are reachable through the documented UI
workflow:

* `contains` builds `expr.ilike('%value%')`, but `resolve_column` types the
  expression as NUMERIC/DATE/BOOLEAN for those column kinds. Postgres has no
  `numeric ~~* unknown` operator, so filtering "contains" on an amount was an
  unhandled `ProgrammingError`.
* A generic page casts `data ->> key` to NUMERIC/DATE/BOOLEAN on *every* row.
  `POST /columns/{id}/narrow-dry-run` is explicitly informational — it
  "never mutates or deletes anything" — and `PATCH /columns/{id}` with
  `confirm_narrow=true` changes the declared type without converting or
  removing the rows that would fail. So an Owner can narrow TEXT -> NUMBER
  over free text, exactly as the dry-run invites them to, and every
  subsequent query on that page fails on the cast. The page is then bricked:
  it cannot be listed, filtered, sorted or totalled, and there is no way back
  through the API because reading it is what fails.

A bad value must read as empty, the way an unevaluatable formula already
does — never take the whole page down.
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


async def _page(client: AsyncClient, headers: dict[str, str], columns: list[dict]) -> str:
    resp = await client.post(
        "/pages",
        json={"name": f"Q {uuid.uuid4().hex[:6]}", "columns": columns},
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


class TestContainsOnANonTextColumn:
    @pytest.mark.parametrize(
        ("data_type", "value", "filter_value"),
        [
            ("CURRENCY", "10.00", "10"),
            ("NUMBER", "42", "4"),
            ("DATE", "2026-09-01", "2026"),
            ("BOOLEAN", "true", "tru"),
        ],
    )
    async def test_it_is_a_422_not_a_500(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        data_type: str,
        value: str,
        filter_value: str,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _page(
            client, headers, [{"name": "Field", "data_type": data_type}]
        )
        await _create(client, headers, page_id, {"field": value})

        resp = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "field", "op": "contains", "value": filter_value}]},
            headers=headers,
        )
        assert resp.status_code == 422, f"expected a clean rejection, got {resp.status_code}"

    async def test_contains_still_works_on_text(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _page(client, headers, [{"name": "Note", "data_type": "TEXT"}])
        wanted = await _create(client, headers, page_id, {"note": "Kandy Wholesale"})
        await _create(client, headers, page_id, {"note": "Colombo Traders"})

        resp = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "note", "op": "contains", "value": "Kandy"}]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert [item["id"] for item in resp.json()["items"]] == [wanted]


class TestSearchMeansTheSameThingOnBothBackends:
    """Search used to match `cast(Record.data, Text)` on a generic page —
    the whole JSONB blob, *including the key names*. So searching for a word
    that happened to be a column key matched every row on the page, and
    searches also hit raw UUIDs and stored dates. A system page meanwhile
    matched only its text columns."""

    async def test_a_column_key_is_not_matched_as_content(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _page(
            client,
            headers,
            [
                {"name": "Note", "data_type": "TEXT"},
                {"name": "Amount", "data_type": "CURRENCY"},
            ],
        )
        await _create(client, headers, page_id, {"note": "rent", "amount": "10.00"})
        await _create(client, headers, page_id, {"note": "fuel", "amount": "20.00"})

        # "amount" is a column key, not a value anyone typed.
        resp = await client.post(
            f"/pages/{page_id}/records/query", json={"search": "amount"}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"] == [], "search matched the column key itself"

    async def test_text_values_are_still_found(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _page(
            client,
            headers,
            [
                {"name": "Note", "data_type": "TEXT"},
                {"name": "Amount", "data_type": "CURRENCY"},
            ],
        )
        wanted = await _create(
            client, headers, page_id, {"note": "Ceylon Electricity", "amount": "10.00"}
        )
        await _create(client, headers, page_id, {"note": "fuel", "amount": "20.00"})

        resp = await client.post(
            f"/pages/{page_id}/records/query", json={"search": "electricity"}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        assert [item["id"] for item in resp.json()["items"]] == [wanted]

    async def test_a_page_with_no_text_columns_returns_nothing_rather_than_everything(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _page(client, headers, [{"name": "Amount", "data_type": "CURRENCY"}])
        await _create(client, headers, page_id, {"amount": "10.00"})

        resp = await client.post(
            f"/pages/{page_id}/records/query", json={"search": "10"}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"] == []


class TestAColumnNarrowedOverIncompatibleData:
    """The bricked-page case, driven entirely through the public API."""

    @staticmethod
    async def _narrow_to_number(
        client: AsyncClient, headers: dict[str, str], page_id: str
    ) -> None:
        schema = await client.get(f"/pages/{page_id}/schema", headers=headers)
        assert schema.status_code == 200, schema.text
        column_id = next(c["id"] for c in schema.json()["columns"] if c["key"] == "field")

        # The dry run is informational and explicitly changes nothing.
        dry = await client.post(
            f"/columns/{column_id}/narrow-dry-run",
            json={"data_type": "NUMBER"},
            headers=headers,
        )
        assert dry.status_code == 200, dry.text
        # It reports the damage and leaves the data exactly as it is.
        assert dry.json()["would_fail"] >= 1

        narrowed = await client.patch(
            f"/columns/{column_id}",
            json={"data_type": "NUMBER", "confirm_narrow": True},
            headers=headers,
        )
        assert narrowed.status_code == 200, narrowed.text

    async def test_listing_the_page_still_works(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _page(client, headers, [{"name": "Field", "data_type": "TEXT"}])
        await _create(client, headers, page_id, {"field": "not a number at all"})
        await _create(client, headers, page_id, {"field": "123"})
        await self._narrow_to_number(client, headers, page_id)

        resp = await client.post(
            f"/pages/{page_id}/records/query", json={}, headers=headers
        )
        assert resp.status_code == 200, f"the page became unreadable: {resp.text}"
        assert len(resp.json()["items"]) == 2

    async def test_sorting_by_the_narrowed_column_still_works(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _page(client, headers, [{"name": "Field", "data_type": "TEXT"}])
        await _create(client, headers, page_id, {"field": "not a number"})
        await _create(client, headers, page_id, {"field": "5"})
        await self._narrow_to_number(client, headers, page_id)

        resp = await client.post(
            f"/pages/{page_id}/records/query",
            json={"sort": [{"column": "field", "direction": "asc"}]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["items"]) == 2

    async def test_totalling_the_narrowed_column_still_works(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """The unconvertible value reads as empty and is simply not summed."""
        headers = await _owner_headers(client, owner_password)
        page_id = await _page(client, headers, [{"name": "Field", "data_type": "TEXT"}])
        await _create(client, headers, page_id, {"field": "junk"})
        await _create(client, headers, page_id, {"field": "10"})
        await self._narrow_to_number(client, headers, page_id)

        resp = await client.post(
            f"/pages/{page_id}/aggregate",
            json={"metric": "sum", "column": "field"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["value"] == "10"

    async def test_filtering_the_narrowed_column_still_works(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _page(client, headers, [{"name": "Field", "data_type": "TEXT"}])
        await _create(client, headers, page_id, {"field": "junk"})
        keep = await _create(client, headers, page_id, {"field": "10"})
        await self._narrow_to_number(client, headers, page_id)

        resp = await client.post(
            f"/pages/{page_id}/records/query",
            json={"filters": [{"column": "field", "op": "gte", "value": "5"}]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert [item["id"] for item in resp.json()["items"]] == [keep]


class TestEnumBackedSelectColumns:
    """`cheques.cheque_status` is a SELECT column on the page schema but a
    Postgres **enum** in the native table (migration 0008).

    Widening search and `contains` to cover SELECT columns introduced a 500
    here: there is no implicit enum-to-text cast, so `ilike` on the column
    raised `operator does not exist: cheque_status ~~* unknown` — in the very
    guard added to turn that class of error into a 422.
    """

    async def test_search_on_the_cheques_page_does_not_500(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        system_page_ids: dict[str, str],
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        resp = await client.post(
            f"/pages/{system_page_ids['cheques']}/records/query",
            json={"search": "pend"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

    async def test_contains_on_an_enum_backed_select_does_not_500(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        system_page_ids: dict[str, str],
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        resp = await client.post(
            f"/pages/{system_page_ids['cheques']}/records/query",
            json={
                "filters": [
                    {"column": "cheque_status", "op": "contains", "value": "PEND"}
                ]
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text


class TestColumnValuesAlwaysReturnsStrings:
    """`ColumnValuesResponse.values` is `list[str]` and Pydantic v2 does not
    coerce. Switching from `str(v)` to `to_wire_value` made a BOOLEAN column
    return a real `bool` and a FORMULA column a `Decimal`, so the filter
    picker 500'd on exactly the pages that had one."""

    @pytest.mark.parametrize(
        ("data_type", "value", "expected"),
        [
            ("BOOLEAN", "true", "true"),
            ("CURRENCY", "1500.00", "1500.00"),
            ("NUMBER", "42", "42"),
            ("TEXT", "Kandy", "Kandy"),
        ],
    )
    async def test_values_are_strings(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        data_type: str,
        value: str,
        expected: str,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _page(client, headers, [{"name": "Field", "data_type": data_type}])
        await _create(client, headers, page_id, {"field": value})

        resp = await client.get(f"/pages/{page_id}/column-values/field", headers=headers)
        assert resp.status_code == 200, resp.text
        values = resp.json()["values"]
        assert all(isinstance(v, str) for v in values), values
        assert expected in values

    async def test_a_formula_column_does_not_500(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _page(
            client,
            headers,
            [
                {"name": "Amount", "data_type": "CURRENCY", "is_required": True},
                {
                    "name": "Doubled",
                    "data_type": "FORMULA",
                    "config": {"expression": "amount * 2"},
                },
            ],
        )
        await _create(client, headers, page_id, {"amount": "10.00"})

        resp = await client.get(f"/pages/{page_id}/column-values/doubled", headers=headers)
        assert resp.status_code == 200, resp.text
        assert all(isinstance(v, str) for v in resp.json()["values"])
