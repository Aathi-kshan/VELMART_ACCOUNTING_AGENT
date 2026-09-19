"""SYSTEM_PAGE_IMMUTABLE (plan sections 3.5.4, 10.3; docs/API.md §1.7) — a
system page's schema changes only by migration, never through the API:
no renaming/archiving the page itself, no adding/editing/removing a column.
`page_service.update_page`/`archive_page` and `schema_service.add_column`/
`update_column` already enforce this (P3); this is the dedicated test the
P3.5 plan asks for, run against a page actually seeded by
`register_system_pages` rather than a synthetic one.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
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


async def test_patching_a_system_page_is_rejected(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = system_page_ids["cheques"]
    resp = await client.patch(f"/pages/{page_id}", json={"name": "Renamed"}, headers=headers)
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "SYSTEM_PAGE_IMMUTABLE"


async def test_deleting_a_system_page_is_rejected(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = system_page_ids["expenses"]
    resp = await client.delete(f"/pages/{page_id}", headers=headers)
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "SYSTEM_PAGE_IMMUTABLE"


async def test_adding_a_column_to_a_system_page_is_rejected(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = system_page_ids["purchases"]
    resp = await client.post(
        f"/pages/{page_id}/columns",
        json={"name": "Extra", "data_type": "TEXT"},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "SYSTEM_PAGE_IMMUTABLE"


async def test_editing_a_system_page_column_is_rejected(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    session: AsyncSession,
    system_page_ids: dict[str, str],
) -> None:
    from sqlalchemy import text

    headers = await _owner_headers(client, owner_password)
    result = await session.execute(
        text("SELECT id FROM page_columns WHERE page_id = :page_id AND key = 'cheque_status'"),
        {"page_id": system_page_ids["cheques"]},
    )
    column_id = result.scalar_one()

    resp = await client.patch(
        f"/columns/{column_id}", json={"name": "Status Renamed"}, headers=headers
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "SYSTEM_PAGE_IMMUTABLE"
