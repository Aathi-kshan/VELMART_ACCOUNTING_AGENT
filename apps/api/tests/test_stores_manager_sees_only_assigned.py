"""GET /stores is the 🟡 filtered case plan section 4.2 excludes from the
blanket permission matrix (test_permissions_matrix.py): a manager never gets
a 403 here, but sees only the stores they're assigned to, never every store
in the company. An owner sees all of them regardless of assignment.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def store_a(session: AsyncSession, company: uuid.UUID) -> uuid.UUID:
    store_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO stores (id, company_id, code, name) "
            "VALUES (:id, :company_id, 'A', 'Store A')"
        ),
        {"id": str(store_id), "company_id": str(company)},
    )
    await session.commit()
    return store_id


@pytest.fixture
async def store_b(session: AsyncSession, company: uuid.UUID) -> uuid.UUID:
    store_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO stores (id, company_id, code, name) "
            "VALUES (:id, :company_id, 'B', 'Store B')"
        ),
        {"id": str(store_id), "company_id": str(company)},
    )
    await session.commit()
    return store_id


@pytest.fixture
async def manager_assigned_to_a(
    session: AsyncSession, manager: uuid.UUID, store_a: uuid.UUID
) -> None:
    await session.execute(
        text("INSERT INTO user_stores (user_id, store_id) VALUES (:uid, :sid)"),
        {"uid": str(manager), "sid": str(store_a)},
    )
    await session.commit()


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": "d1"}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


async def test_manager_sees_only_assigned_store(
    client: AsyncClient,
    manager: uuid.UUID,
    manager_password: str,
    manager_assigned_to_a: None,
    store_a: uuid.UUID,
    store_b: uuid.UUID,
) -> None:
    token = await _login(client, "manager@test.lk", manager_password)
    resp = await client.get("/stores", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert ids == {str(store_a)}


async def test_manager_with_no_assignment_sees_nothing_not_403(
    client: AsyncClient, manager: uuid.UUID, manager_password: str, store_a: uuid.UUID
) -> None:
    token = await _login(client, "manager@test.lk", manager_password)
    resp = await client.get("/stores", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_owner_sees_every_store_regardless_of_assignment(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager_assigned_to_a: None,
    store_a: uuid.UUID,
    store_b: uuid.UUID,
) -> None:
    token = await _login(client, "owner@test.lk", owner_password)
    resp = await client.get("/stores", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert ids == {str(store_a), str(store_b)}
