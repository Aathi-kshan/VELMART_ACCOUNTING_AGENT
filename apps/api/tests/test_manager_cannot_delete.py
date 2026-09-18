"""`DELETE /records/{record_id}` is Owner-only — a manager can add records
but never remove one, including one they created themselves. Deletion here
is the platform's soft-delete-with-reason (plan section 4.4); this proves a
denied attempt leaves the record fully `ACTIVE`, not partially voided.
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


async def test_manager_cannot_delete_a_record_they_created_themselves(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
    session: AsyncSession,
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    page_id = await _owner_creates_page_with_grant(client, owner_headers, manager)

    manager_headers = await _manager_headers(client, manager_password)
    created = await client.post(
        f"/pages/{page_id}/records",
        json={
            "occurred_at": "2026-09-02T10:00:00+05:30",
            "data": {"supplier_name": "Colombo FMCG"},
        },
        headers=manager_headers,
    )
    assert created.status_code == 201, created.text
    record = created.json()

    resp = await client.request(
        "DELETE",
        f"/records/{record['id']}",
        json={"reason": "no longer needed"},
        headers=manager_headers,
    )

    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "PERMISSION_DENIED"

    row = (
        await session.execute(
            text("SELECT status FROM records WHERE id = :id"), {"id": record["id"]}
        )
    ).one()
    assert row.status == "ACTIVE", "A denied delete must not change record status at all"


async def test_manager_delete_denial_is_audited(
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
    created = await client.post(
        f"/pages/{page_id}/records",
        json={"occurred_at": "2026-09-02T10:00:00+05:30", "data": {"supplier_name": "Test Co"}},
        headers=owner_headers,
    )
    record = created.json()

    manager_headers = await _manager_headers(client, manager_password)
    resp = await client.request(
        "DELETE", f"/records/{record['id']}", json={"reason": "x"}, headers=manager_headers
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


async def test_owner_can_delete_the_same_record_a_manager_was_blocked_from(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    page_id = await _owner_creates_page_with_grant(client, owner_headers, manager)
    created = await client.post(
        f"/pages/{page_id}/records",
        json={"occurred_at": "2026-09-02T10:00:00+05:30", "data": {"supplier_name": "Deletable"}},
        headers=owner_headers,
    )
    record = created.json()

    manager_headers = await _manager_headers(client, manager_password)
    blocked = await client.request(
        "DELETE", f"/records/{record['id']}", json={"reason": "attempt"}, headers=manager_headers
    )
    assert blocked.status_code == 403

    resp = await client.request(
        "DELETE",
        f"/records/{record['id']}",
        json={"reason": "owner approved removal"},
        headers=owner_headers,
    )
    assert resp.status_code == 204, resp.text
