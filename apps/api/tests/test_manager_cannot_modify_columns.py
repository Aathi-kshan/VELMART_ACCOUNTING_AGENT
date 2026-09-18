"""Schema configuration — `POST /pages/{id}/columns`, `PATCH /columns/{id}`,
`DELETE /columns/{id}`, `POST /columns/{id}/narrow-dry-run` — is Owner-only
(design.md §14: "Managers ... cannot configure pages"). A manager with full
`can_view`/`can_create` access to a page still cannot touch its structure;
that split is exactly what proves this is a role gate, not a page-access
gate.
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
) -> dict:
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
    page = created.json()
    grant = await client.put(
        f"/pages/{page['id']}/access",
        json={"grants": [{"user_id": str(manager_id), "can_view": True, "can_create": True}]},
        headers=owner_headers,
    )
    assert grant.status_code == 200, grant.text
    return page


async def test_manager_cannot_add_a_column(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
    session: AsyncSession,
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    page = await _owner_creates_page_with_grant(client, owner_headers, manager)

    manager_headers = await _manager_headers(client, manager_password)
    resp = await client.post(
        f"/pages/{page['id']}/columns",
        json={"name": "Credit Limit", "data_type": "CURRENCY"},
        headers=manager_headers,
    )

    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "PERMISSION_DENIED"

    count = (
        await session.execute(
            text("SELECT count(*) FROM page_columns WHERE page_id = :pid"), {"pid": page["id"]}
        )
    ).scalar_one()
    assert count == 1, "Only the one column the Owner created should exist"


async def test_manager_cannot_rename_a_column(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    page = await _owner_creates_page_with_grant(client, owner_headers, manager)
    column_id = page["columns"][0]["id"]

    manager_headers = await _manager_headers(client, manager_password)
    resp = await client.patch(
        f"/columns/{column_id}", json={"name": "Renamed"}, headers=manager_headers
    )

    assert resp.status_code == 403, resp.text

    still = await client.get(f"/pages/{page['id']}/schema", headers=owner_headers)
    assert still.json()["columns"][0]["name"] == "Supplier Name"


async def test_manager_cannot_archive_a_column(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    page = await _owner_creates_page_with_grant(client, owner_headers, manager)
    column_id = page["columns"][0]["id"]

    manager_headers = await _manager_headers(client, manager_password)
    resp = await client.delete(f"/columns/{column_id}", headers=manager_headers)

    assert resp.status_code == 403, resp.text

    still = await client.get(f"/pages/{page['id']}/schema", headers=owner_headers)
    assert still.json()["columns"][0]["is_archived"] is False


async def test_manager_cannot_run_a_narrow_dry_run(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    page = await _owner_creates_page_with_grant(client, owner_headers, manager)
    column_id = page["columns"][0]["id"]

    manager_headers = await _manager_headers(client, manager_password)
    resp = await client.post(
        f"/columns/{column_id}/narrow-dry-run",
        json={"data_type": "TEXT"},
        headers=manager_headers,
    )

    assert resp.status_code == 403, resp.text


async def test_manager_column_denial_is_audited(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
    company: uuid.UUID,
    session: AsyncSession,
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    page = await _owner_creates_page_with_grant(client, owner_headers, manager)

    manager_headers = await _manager_headers(client, manager_password)
    resp = await client.post(
        f"/pages/{page['id']}/columns",
        json={"name": "Notes", "data_type": "TEXT"},
        headers=manager_headers,
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


async def test_owner_can_add_the_column_a_manager_was_blocked_from(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    page = await _owner_creates_page_with_grant(client, owner_headers, manager)

    manager_headers = await _manager_headers(client, manager_password)
    blocked = await client.post(
        f"/pages/{page['id']}/columns",
        json={"name": "Credit Limit", "data_type": "CURRENCY"},
        headers=manager_headers,
    )
    assert blocked.status_code == 403

    resp = await client.post(
        f"/pages/{page['id']}/columns",
        json={"name": "Credit Limit", "data_type": "CURRENCY"},
        headers=owner_headers,
    )
    assert resp.status_code == 201, resp.text
