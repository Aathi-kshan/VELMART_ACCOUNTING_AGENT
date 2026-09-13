"""`RECORD_REF` resolution, integrity, and delete blocking (plan section
11.2, P4 §5) — `app/services/reference_service.py`. Config-shape validation
(`target_page_key`/`display_column` must name real things at column-save
time) is `test_page_engine.py`'s territory; this file is the record-level
existence check and delete blocking.
"""

from __future__ import annotations

import uuid

import pytest
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


async def _owner_headers_for(client: AsyncClient, password: str) -> dict[str, str]:
    token = await _login(client, "owner-b@test.lk", password)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def company_b(session: AsyncSession) -> uuid.UUID:
    company_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO companies (id, name) VALUES (:id, 'Other Supermarket')"),
        {"id": str(company_id)},
    )
    await session.commit()
    return company_id


@pytest.fixture
async def owner_b_password() -> str:
    return "correct-horse-battery-b"


@pytest.fixture
async def owner_b(session: AsyncSession, company_b: uuid.UUID, owner_b_password: str) -> uuid.UUID:
    from app.core.security import hash_password

    user_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO users (id, company_id, email, full_name, password_hash, role)
            VALUES (:id, :company_id, :email, 'Other Owner', :pw, 'OWNER')
            """
        ),
        {
            "id": str(user_id),
            "company_id": str(company_b),
            "email": "owner-b@test.lk",
            "pw": hash_password(owner_b_password),
        },
    )
    await session.commit()
    return user_id


async def _create_suppliers_page(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/pages",
        json={
            "name": "Suppliers",
            "columns": [{"name": "Supplier Name", "data_type": "TEXT", "is_required": True}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _create_supplier_record(
    client: AsyncClient, headers: dict[str, str], page_id: str, name: str
) -> str:
    resp = await client.post(
        f"/pages/{page_id}/records",
        json={
            "occurred_at": "2026-09-07T10:00:00+05:30",
            "data": {"supplier_name": name},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _create_purchases_page(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/pages",
        json={
            "name": "Purchases2",
            "columns": [
                {"name": "Amount", "data_type": "CURRENCY", "is_required": True},
                {
                    "name": "Supplier",
                    "data_type": "RECORD_REF",
                    "config": {
                        "target_page_key": "suppliers",
                        "display_column": "supplier_name",
                    },
                },
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


class TestExistenceOnWrite:
    async def test_valid_reference_accepted_on_create(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        suppliers_id = await _create_suppliers_page(client, headers)
        supplier_id = await _create_supplier_record(client, headers, suppliers_id, "Acme Ltd")
        purchases_id = await _create_purchases_page(client, headers)

        resp = await client.post(
            f"/pages/{purchases_id}/records",
            json={
                "occurred_at": "2026-09-07T10:00:00+05:30",
                "data": {"amount": "100.00", "supplier": supplier_id},
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["supplier"] == supplier_id

    async def test_nonexistent_reference_rejected_on_create(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        await _create_suppliers_page(client, headers)
        purchases_id = await _create_purchases_page(client, headers)

        resp = await client.post(
            f"/pages/{purchases_id}/records",
            json={
                "occurred_at": "2026-09-07T10:00:00+05:30",
                "data": {"amount": "100.00", "supplier": str(uuid.uuid4())},
            },
            headers=headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "REFERENCE_NOT_FOUND"

    async def test_reference_to_a_record_on_the_wrong_page_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        await _create_suppliers_page(client, headers)
        purchases_id = await _create_purchases_page(client, headers)

        # A record that genuinely exists, but on `purchases_id` itself, not
        # `suppliers` — the configured target page.
        other_record = await client.post(
            f"/pages/{purchases_id}/records",
            json={
                "occurred_at": "2026-09-07T10:00:00+05:30",
                "data": {"amount": "1.00"},
            },
            headers=headers,
        )
        assert other_record.status_code == 201, other_record.text
        wrong_page_id = other_record.json()["id"]

        resp = await client.post(
            f"/pages/{purchases_id}/records",
            json={
                "occurred_at": "2026-09-07T10:00:00+05:30",
                "data": {"amount": "100.00", "supplier": wrong_page_id},
            },
            headers=headers,
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "REFERENCE_NOT_FOUND"

    async def test_reference_to_a_record_in_another_company_rejected_identically(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        owner_b: uuid.UUID,
        owner_b_password: str,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        await _create_suppliers_page(client, headers)
        purchases_id = await _create_purchases_page(client, headers)

        # A real supplier record, but it lives in company B's own "Suppliers"
        # page — never visible to company A no matter how well-formed its id.
        headers_b = await _owner_headers_for(client, owner_b_password)
        suppliers_b_id = await _create_suppliers_page(client, headers_b)
        supplier_in_b = await _create_supplier_record(
            client, headers_b, suppliers_b_id, "Foreign Supplier"
        )

        resp = await client.post(
            f"/pages/{purchases_id}/records",
            json={
                "occurred_at": "2026-09-07T10:00:00+05:30",
                "data": {"amount": "100.00", "supplier": supplier_in_b},
            },
            headers=headers,
        )
        assert resp.status_code == 422, resp.text
        # Identical code/shape to a target that simply doesn't exist —
        # never a different error that would leak "it exists, just not here".
        assert resp.json()["code"] == "REFERENCE_NOT_FOUND"

    async def test_existence_checked_on_update_too(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        suppliers_id = await _create_suppliers_page(client, headers)
        supplier_id = await _create_supplier_record(client, headers, suppliers_id, "Acme Ltd")
        purchases_id = await _create_purchases_page(client, headers)

        create = await client.post(
            f"/pages/{purchases_id}/records",
            json={
                "occurred_at": "2026-09-07T10:00:00+05:30",
                "data": {"amount": "100.00", "supplier": supplier_id},
            },
            headers=headers,
        )
        assert create.status_code == 201, create.text
        record_id = create.json()["id"]

        patch = await client.patch(
            f"/records/{record_id}",
            json={"data": {"supplier": str(uuid.uuid4())}},
            headers={**headers, "If-Match": "1"},
        )
        assert patch.status_code == 422, patch.text
        assert patch.json()["code"] == "REFERENCE_NOT_FOUND"


class TestDeleteBlocking:
    async def test_deleting_a_referenced_record_is_blocked(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        suppliers_id = await _create_suppliers_page(client, headers)
        supplier_id = await _create_supplier_record(client, headers, suppliers_id, "Acme Ltd")
        purchases_id = await _create_purchases_page(client, headers)
        await client.post(
            f"/pages/{purchases_id}/records",
            json={
                "occurred_at": "2026-09-07T10:00:00+05:30",
                "data": {"amount": "100.00", "supplier": supplier_id},
            },
            headers=headers,
        )

        resp = await client.request(
            "DELETE",
            f"/records/{supplier_id}",
            json={"reason": "no longer needed"},
            headers=headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "REFERENCED_RECORD_EXISTS"

    async def test_deleting_an_unreferenced_record_succeeds(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        suppliers_id = await _create_suppliers_page(client, headers)
        supplier_id = await _create_supplier_record(client, headers, suppliers_id, "Acme Ltd")

        resp = await client.request(
            "DELETE",
            f"/records/{supplier_id}",
            json={"reason": "duplicate entry"},
            headers=headers,
        )
        assert resp.status_code == 204, resp.text
