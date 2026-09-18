"""`POST /pages/{id}/export` is Owner-only (plan section 13.2 / P3.5 Part 2,
design.md §14.2: export is removed from Manager navigation entirely). A
manager with full view/create access to a page still cannot pull its CSV.
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


async def _owner_creates_page_with_grant(
    client: AsyncClient, owner_headers: dict[str, str], manager_id: uuid.UUID
) -> str:
    created = await client.post(
        "/pages",
        json={
            "name": "Supplier Contacts",
            "kind": "REGISTER",
            "columns": [{"name": "Supplier Name", "data_type": "TEXT"}],
        },
        headers=owner_headers,
    )
    assert created.status_code == 201, created.text
    page_id = created.json()["id"]
    grant = await client.put(
        f"/pages/{page_id}/access",
        json={"grants": [{"user_id": str(manager_id), "can_view": True, "can_create": True}]},
        headers=owner_headers,
    )
    assert grant.status_code == 200, grant.text
    return page_id


async def test_manager_with_full_page_access_cannot_export(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    page_id = await _owner_creates_page_with_grant(client, owner_headers, manager)

    manager_headers = await _manager_headers(client, manager_password)
    resp = await client.post(f"/pages/{page_id}/export", json={}, headers=manager_headers)

    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "PERMISSION_DENIED"


async def test_manager_export_denial_is_audited(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
    company: uuid.UUID,
    session: AsyncSession,
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    page_id = await _owner_creates_page_with_grant(client, owner_headers, manager)

    manager_headers = await _manager_headers(client, manager_password)
    resp = await client.post(f"/pages/{page_id}/export", json={}, headers=manager_headers)
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


async def test_owner_can_export_the_same_page_a_manager_was_blocked_from(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    page_id = await _owner_creates_page_with_grant(client, owner_headers, manager)
    manager_headers = await _manager_headers(client, manager_password)

    blocked = await client.post(f"/pages/{page_id}/export", json={}, headers=manager_headers)
    assert blocked.status_code == 403

    resp = await client.post(f"/pages/{page_id}/export", json={}, headers=owner_headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
