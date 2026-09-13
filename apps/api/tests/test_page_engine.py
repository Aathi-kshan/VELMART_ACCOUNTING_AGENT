"""Page/column schema management (plan sections 3.1-3.5, 10.1-10.3).

FORMULA/ATTACHMENT are schema-definable here (all 15 types) even though
their *value* handling is out of scope for P3 (see the P3 plan's Context
section) — evaluating a formula and accepting an attachment count are both
later phases; defining the column itself is not.
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


_ALL_TYPE_COLUMNS = [
    {"name": "Text Col", "data_type": "TEXT"},
    {"name": "Long Text Col", "data_type": "LONG_TEXT"},
    {"name": "Number Col", "data_type": "NUMBER"},
    {"name": "Currency Col", "data_type": "CURRENCY"},
    {"name": "Percent Col", "data_type": "PERCENT"},
    {"name": "Date Col", "data_type": "DATE"},
    {"name": "Datetime Col", "data_type": "DATETIME"},
    {"name": "Boolean Col", "data_type": "BOOLEAN"},
    {"name": "Select Col", "data_type": "SELECT", "config": {"options": ["A", "B"]}},
    {"name": "Multi Select Col", "data_type": "MULTI_SELECT", "config": {"options": ["X", "Y"]}},
    # A self-reference (target = the page being created) is the one case
    # `page_service.validate_column_config` can't check for existence yet —
    # the page doesn't have a row until this create call returns — so it's
    # also the only target this fixture can name without depending on some
    # other page already existing.
    {
        "name": "Record Ref Col",
        "data_type": "RECORD_REF",
        "config": {"target_page_key": "everything_page"},
    },
    {"name": "Store Ref Col", "data_type": "STORE_REF"},
    {"name": "User Ref Col", "data_type": "USER_REF"},
    {"name": "Formula Col", "data_type": "FORMULA", "config": {"expression": "1+1"}},
    {"name": "Attachment Col", "data_type": "ATTACHMENT"},
]


class TestPageCreation:
    async def test_create_page_with_every_column_type(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        resp = await client.post(
            "/pages",
            json={"name": "Everything Page", "columns": _ALL_TYPE_COLUMNS},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["key"] == "everything_page"
        assert len(body["columns"]) == len(_ALL_TYPE_COLUMNS)
        keys = {c["key"] for c in body["columns"]}
        assert keys == {
            "text_col", "long_text_col", "number_col", "currency_col", "percent_col",
            "date_col", "datetime_col", "boolean_col", "select_col", "multi_select_col",
            "record_ref_col", "store_ref_col", "user_ref_col", "formula_col", "attachment_col",
        }

    async def test_reserved_page_key_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        resp = await client.post("/pages", json={"name": "Cheque", "columns": []}, headers=headers)
        assert resp.status_code == 409
        assert resp.json()["code"] == "RESERVED_PAGE_KEY"

    async def test_duplicate_page_name_is_conflict(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        payload = {"name": "Expenses Log", "columns": []}
        first = await client.post("/pages", json=payload, headers=headers)
        assert first.status_code == 201
        second = await client.post("/pages", json=payload, headers=headers)
        assert second.status_code == 409

    async def test_select_column_without_options_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        resp = await client.post(
            "/pages",
            json={
                "name": "Bad Select Page",
                "columns": [{"name": "Status", "data_type": "SELECT"}],
            },
            headers=headers,
        )
        assert resp.status_code == 422


class TestColumnKeyImmutability:
    async def test_changing_key_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        create = await client.post(
            "/pages",
            json={"name": "Immutable Page", "columns": [{"name": "Amount", "data_type": "TEXT"}]},
            headers=headers,
        )
        column_id = create.json()["columns"][0]["id"]

        resp = await client.patch(
            f"/columns/{column_id}", json={"key": "something_else"}, headers=headers
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "COLUMN_KEY_IMMUTABLE"


class TestSchemaEvolution:
    async def test_rename_reorder_and_archive_column(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        create = await client.post(
            "/pages",
            json={
                "name": "Evolving Page",
                "columns": [
                    {"name": "First", "data_type": "TEXT"},
                    {"name": "Second", "data_type": "TEXT"},
                ],
            },
            headers=headers,
        )
        columns = create.json()["columns"]
        first_id = next(c["id"] for c in columns if c["key"] == "first")

        rename = await client.patch(
            f"/columns/{first_id}", json={"name": "First Renamed"}, headers=headers
        )
        assert rename.status_code == 200
        assert rename.json()["name"] == "First Renamed"
        assert rename.json()["key"] == "first"  # key survives the rename

        reorder = await client.patch(
            f"/columns/{first_id}", json={"position": 5}, headers=headers
        )
        assert reorder.status_code == 200
        assert reorder.json()["position"] == 5

        archive = await client.delete(f"/columns/{first_id}", headers=headers)
        assert archive.status_code == 200
        assert archive.json()["is_archived"] is True

        schema = await client.get(f"/pages/{create.json()['id']}/schema", headers=headers)
        assert [c["key"] for c in schema.json()["columns"]] == ["second"]

    async def test_add_column_leaves_existing_records_null(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        create = await client.post(
            "/pages",
            json={"name": "Growing Page", "columns": [{"name": "Note", "data_type": "TEXT"}]},
            headers=headers,
        )
        page_id = create.json()["id"]

        record = await client.post(
            f"/pages/{page_id}/records",
            json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"note": "hello"}},
            headers=headers,
        )
        assert record.status_code == 201, record.text

        add_col = await client.post(
            f"/pages/{page_id}/columns",
            json={"name": "New Field", "data_type": "TEXT"},
            headers=headers,
        )
        assert add_col.status_code == 201

        fetched = await client.get(f"/records/{record.json()['id']}", headers=headers)
        assert "new_field" not in fetched.json()["data"]

    async def test_removing_select_option_in_use_warns_but_succeeds(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        create = await client.post(
            "/pages",
            json={
                "name": "Status Page",
                "columns": [
                    {
                        "name": "Status",
                        "data_type": "SELECT",
                        "config": {"options": ["Open", "Closed"]},
                    }
                ],
            },
            headers=headers,
        )
        page_id = create.json()["id"]
        column_id = create.json()["columns"][0]["id"]

        await client.post(
            f"/pages/{page_id}/records",
            json={
                "occurred_at": "2026-09-07T10:00:00+05:30",
                "data": {"status": "Open"},
            },
            headers=headers,
        )

        update = await client.patch(
            f"/columns/{column_id}",
            json={"config": {"options": ["Closed"]}},
            headers=headers,
        )
        assert update.status_code == 200
        assert update.json()["removed_options_in_use"] == {"Open": 1}

    async def test_narrow_dry_run_reports_failures_and_writes_nothing(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        create = await client.post(
            "/pages",
            json={"name": "Narrow Page", "columns": [{"name": "Value", "data_type": "TEXT"}]},
            headers=headers,
        )
        page_id = create.json()["id"]
        column_id = create.json()["columns"][0]["id"]

        await client.post(
            f"/pages/{page_id}/records",
            json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"value": "not-a-number"}},
            headers=headers,
        )
        await client.post(
            f"/pages/{page_id}/records",
            json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"value": "42"}},
            headers=headers,
        )

        dry_run = await client.post(
            f"/columns/{column_id}/narrow-dry-run",
            json={"data_type": "NUMBER"},
            headers=headers,
        )
        assert dry_run.status_code == 200
        assert dry_run.json()["would_fail"] == 1

        # The dry run must not have changed the column's actual type.
        schema = await client.get(f"/pages/{page_id}/schema", headers=headers)
        assert schema.json()["columns"][0]["data_type"] == "TEXT"

    async def test_narrowing_without_confirm_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        create = await client.post(
            "/pages",
            json={"name": "Confirm Page", "columns": [{"name": "Value", "data_type": "TEXT"}]},
            headers=headers,
        )
        column_id = create.json()["columns"][0]["id"]

        resp = await client.patch(
            f"/columns/{column_id}", json={"data_type": "NUMBER"}, headers=headers
        )
        assert resp.status_code == 422

        confirmed = await client.patch(
            f"/columns/{column_id}",
            json={"data_type": "NUMBER", "confirm_narrow": True},
            headers=headers,
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["data_type"] == "NUMBER"


class TestProjectionAllocation:
    async def test_fifth_indexed_numeric_column_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        columns = [
            {"name": f"Num{i}", "data_type": "NUMBER", "is_indexed": True} for i in range(4)
        ]
        create = await client.post(
            "/pages", json={"name": "Numeric Page", "columns": columns}, headers=headers
        )
        assert create.status_code == 201
        page_id = create.json()["id"]

        fifth = await client.post(
            f"/pages/{page_id}/columns",
            json={"name": "Num5", "data_type": "NUMBER", "is_indexed": True},
            headers=headers,
        )
        assert fifth.status_code == 409

    async def test_third_indexed_date_column_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        columns = [
            {"name": f"Date{i}", "data_type": "DATE", "is_indexed": True} for i in range(2)
        ]
        create = await client.post(
            "/pages", json={"name": "Date Page", "columns": columns}, headers=headers
        )
        assert create.status_code == 201
        page_id = create.json()["id"]

        third = await client.post(
            f"/pages/{page_id}/columns",
            json={"name": "Date3", "data_type": "DATE", "is_indexed": True},
            headers=headers,
        )
        assert third.status_code == 409
