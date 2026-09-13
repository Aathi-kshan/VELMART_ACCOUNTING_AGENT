"""Record validation against a page's live schema (plan sections 3.6, 9.1,
9.2, 10.4). FORMULA is schema-definable (test_page_engine.py) and never
accepted as input — it's still rejected on write — but from P4 onward it
*is* computed and present on read (`app/services/formula_service.py`); see
`test_formula_engine.py` for the evaluator itself.
"""

from __future__ import annotations

import uuid
from typing import Any

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


async def _create_page(
    client: AsyncClient, headers: dict[str, str], **overrides: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Outgoings",
        "columns": [
            {"name": "Date", "data_type": "DATE", "is_required": True},
            {
                "name": "Category",
                "data_type": "SELECT",
                "config": {"options": ["Electricity", "Rent", "Other"], "default": "Other"},
            },
            {"name": "Amount", "data_type": "CURRENCY", "is_required": True, "config": {"min": 0}},
            {"name": "Store", "data_type": "STORE_REF"},
            {"name": "Total", "data_type": "FORMULA", "config": {"expression": "amount"}},
        ],
    }
    payload.update(overrides)
    resp = await client.post("/pages", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestTypeValidation:
    async def test_valid_record_is_accepted(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers)
        resp = await client.post(
            f"/pages/{page['id']}/records",
            json={
                "occurred_at": "2026-09-07T16:30:00+05:30",
                "data": {"date": "2026-09-07", "category": "Electricity", "amount": "50000.00"},
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["data"]["amount"] == "50000.00"
        assert body["business_date"] == "2026-09-07"
        assert body["version"] == 1

    async def test_missing_required_field_is_422(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers)
        resp = await client.post(
            f"/pages/{page['id']}/records",
            json={"occurred_at": "2026-09-07T16:30:00+05:30", "data": {"category": "Electricity"}},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_float_currency_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers)
        resp = await client.post(
            f"/pages/{page['id']}/records",
            json={
                "occurred_at": "2026-09-07T16:30:00+05:30",
                "data": {"date": "2026-09-07", "amount": 50000.5},
            },
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_negative_currency_without_allow_negative_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers)
        resp = await client.post(
            f"/pages/{page['id']}/records",
            json={
                "occurred_at": "2026-09-07T16:30:00+05:30",
                "data": {"date": "2026-09-07", "amount": "-5.00"},
            },
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_select_value_outside_options_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers)
        resp = await client.post(
            f"/pages/{page['id']}/records",
            json={
                "occurred_at": "2026-09-07T16:30:00+05:30",
                "data": {"date": "2026-09-07", "amount": "1.00", "category": "Bogus"},
            },
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_select_default_applies_when_omitted(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers)
        resp = await client.post(
            f"/pages/{page['id']}/records",
            json={
                "occurred_at": "2026-09-07T16:30:00+05:30",
                "data": {"date": "2026-09-07", "amount": "1.00"},
            },
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["category"] == "Other"

    async def test_unknown_field_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers)
        resp = await client.post(
            f"/pages/{page['id']}/records",
            json={
                "occurred_at": "2026-09-07T16:30:00+05:30",
                "data": {"date": "2026-09-07", "amount": "1.00", "bogus_key": "x"},
            },
            headers=headers,
        )
        assert resp.status_code == 422


class TestReferenceValidation:
    async def test_store_ref_to_a_real_store_succeeds(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        store_resp = await client.post(
            "/stores", json={"code": "S1", "name": "Main Store"}, headers=headers
        )
        assert store_resp.status_code == 201
        store_id = store_resp.json()["id"]

        page = await _create_page(client, headers)
        resp = await client.post(
            f"/pages/{page['id']}/records",
            json={
                "occurred_at": "2026-09-07T16:30:00+05:30",
                "data": {"date": "2026-09-07", "amount": "1.00", "store": store_id},
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

    async def test_store_ref_to_a_nonexistent_store_is_422(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers)
        resp = await client.post(
            f"/pages/{page['id']}/records",
            json={
                "occurred_at": "2026-09-07T16:30:00+05:30",
                "data": {"date": "2026-09-07", "amount": "1.00", "store": str(uuid.uuid4())},
            },
            headers=headers,
        )
        assert resp.status_code == 422


class TestFormulaScopeBoundary:
    async def test_supplying_a_formula_value_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers)
        resp = await client.post(
            f"/pages/{page['id']}/records",
            json={
                "occurred_at": "2026-09-07T16:30:00+05:30",
                "data": {"date": "2026-09-07", "amount": "1.00", "total": "2.00"},
            },
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_formula_is_computed_on_read(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """P4: `total`'s expression is `amount` — a trivial passthrough — so
        it should equal `amount` on both the create response and a
        subsequent fetch, computed fresh each time, never stored."""
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers)
        create = await client.post(
            f"/pages/{page['id']}/records",
            json={
                "occurred_at": "2026-09-07T16:30:00+05:30",
                "data": {"date": "2026-09-07", "amount": "1.00"},
            },
            headers=headers,
        )
        assert create.json()["data"]["total"] == "1.00"

        fetched = await client.get(f"/records/{create.json()['id']}", headers=headers)
        assert fetched.json()["data"]["total"] == "1.00"


class TestBusinessDateDerivation:
    async def test_business_date_from_designated_date_column(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(client, headers, date_column_key="date")
        resp = await client.post(
            f"/pages/{page['id']}/records",
            json={
                "occurred_at": "2026-09-07T23:00:00+05:30",
                "data": {"date": "2026-09-20", "amount": "1.00"},
            },
            headers=headers,
        )
        assert resp.status_code == 201
        # The designated date column wins over occurred_at's own date.
        assert resp.json()["business_date"] == "2026-09-20"

    async def test_business_date_falls_back_to_occurred_at_and_cutoff(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _create_page(
            client,
            headers,
            columns=[
                {"name": "Amount", "data_type": "CURRENCY", "is_required": True},
            ],
        )
        # 00:30 Colombo (+05:30) on the 8th is 19:00 UTC on the 7th, and is
        # before the default 02:00 cutoff, so it posts to the 7th.
        resp = await client.post(
            f"/pages/{page['id']}/records",
            json={"occurred_at": "2026-09-08T00:30:00+05:30", "data": {"amount": "1.00"}},
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["business_date"] == "2026-09-07"


class TestIdempotency:
    async def test_replaying_the_same_key_and_body_returns_the_stored_response(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = {
            **await _owner_headers(client, owner_password),
            "Idempotency-Key": str(uuid.uuid4()),
        }
        page = await _create_page(client, headers)
        body = {
            "occurred_at": "2026-09-07T16:30:00+05:30",
            "data": {"date": "2026-09-07", "amount": "1.00"},
        }
        first = await client.post(f"/pages/{page['id']}/records", json=body, headers=headers)
        second = await client.post(f"/pages/{page['id']}/records", json=body, headers=headers)
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["id"] == second.json()["id"]

    async def test_replaying_the_same_key_with_a_different_body_is_conflict(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        idem_key = str(uuid.uuid4())
        headers = {**await _owner_headers(client, owner_password), "Idempotency-Key": idem_key}
        page = await _create_page(client, headers)
        first = await client.post(
            f"/pages/{page['id']}/records",
            json={
                "occurred_at": "2026-09-07T16:30:00+05:30",
                "data": {"date": "2026-09-07", "amount": "1.00"},
            },
            headers=headers,
        )
        assert first.status_code == 201

        second = await client.post(
            f"/pages/{page['id']}/records",
            json={
                "occurred_at": "2026-09-07T16:30:00+05:30",
                "data": {"date": "2026-09-07", "amount": "2.00"},
            },
            headers=headers,
        )
        assert second.status_code == 409
