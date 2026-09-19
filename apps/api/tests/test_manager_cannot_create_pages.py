"""`POST /pages` is Owner-only (`app/core/permissions.py`'s matrix) — a
manager cannot invent a business table, even one that only holds their own
records. `test_permissions_matrix.py` already proves the bare status code
for a synthetic request; this proves the denial is real (no page is left
behind) and audited, the same depth the AI/protected-field suites give
their own Owner-only routes.
"""

from __future__ import annotations

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


async def test_manager_cannot_create_a_page(
    client: AsyncClient,
    manager: uuid.UUID,
    manager_password: str,
    company: uuid.UUID,
    session: AsyncSession,
) -> None:
    headers = await _manager_headers(client, manager_password)

    resp = await client.post(
        "/pages",
        json={
            "name": "Supplier Contacts",
            "kind": "REGISTER",
            "columns": [{"name": "Supplier Name", "data_type": "TEXT"}],
        },
        headers=headers,
    )

    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "PERMISSION_DENIED"

    rows = (
        await session.execute(
            text(
                "SELECT count(*) FROM pages "
                "WHERE company_id = :cid AND key = 'supplier_contacts'"
            ),
            {"cid": str(company)},
        )
    ).scalar_one()
    assert rows == 0, "A page must not exist after a denied create attempt"


async def test_manager_cannot_archive_a_page(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    created = await client.post(
        "/pages",
        json={
            "name": "Equipment Maintenance",
            "kind": "REGISTER",
            "columns": [{"name": "Equipment Name", "data_type": "TEXT"}],
        },
        headers=owner_headers,
    )
    assert created.status_code == 201, created.text
    page_id = created.json()["id"]

    manager_headers = await _manager_headers(client, manager_password)
    resp = await client.delete(f"/pages/{page_id}", headers=manager_headers)

    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "PERMISSION_DENIED"

    still_there = await client.get(f"/pages/{page_id}/schema", headers=owner_headers)
    assert still_there.status_code == 200
    assert still_there.json()["is_archived"] is False


async def test_manager_page_creation_denial_is_audited(
    client: AsyncClient,
    manager: uuid.UUID,
    manager_password: str,
    company: uuid.UUID,
    session: AsyncSession,
) -> None:
    headers = await _manager_headers(client, manager_password)
    resp = await client.post(
        "/pages",
        json={
            "name": "Denied Page",
            "kind": "REGISTER",
            "columns": [{"name": "X", "data_type": "TEXT"}],
        },
        headers=headers,
    )
    assert resp.status_code == 403

    rows = (
        await session.execute(
            text(
                "SELECT actor_user_id, actor_role FROM audit_logs "
                "WHERE company_id = :cid AND action = 'PERMISSION_DENIED'"
            ),
            {"cid": str(company)},
        )
    ).all()
    assert any(
        str(row.actor_user_id) == str(manager) and row.actor_role == "MANAGER" for row in rows
    )


async def test_owner_can_create_a_page(
    client: AsyncClient, owner: uuid.UUID, owner_password: str
) -> None:
    headers = await _owner_headers(client, owner_password)
    resp = await client.post(
        "/pages",
        json={
            "name": "Supplier Contacts",
            "kind": "REGISTER",
            "columns": [{"name": "Supplier Name", "data_type": "TEXT"}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["key"] == "supplier_contacts"
