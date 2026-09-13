"""A manager's 403 from `require_owner` writes exactly one PERMISSION_DENIED
audit row before raising (plan sections 18.2, 20.2) — durable regardless of
what the caller does with the exception afterward, per
app/dependencies/guards.py's commit-before-raise.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_managers_403_on_owner_only_endpoint_is_audited(
    client: AsyncClient,
    manager: uuid.UUID,
    manager_password: str,
    company: uuid.UUID,
    session: AsyncSession,
) -> None:
    login = await client.post(
        "/auth/login",
        json={"email": "manager@test.lk", "password": manager_password, "device_id": "d1"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    resp = await client.get("/users", headers={"Authorization": f"Bearer {token}"})
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
    assert len(rows) == 1
    assert rows[0].actor_user_id == manager
    assert rows[0].actor_role == "MANAGER"


async def test_denial_survives_even_though_the_request_then_fails(
    client: AsyncClient,
    manager: uuid.UUID,
    manager_password: str,
    company: uuid.UUID,
    session: AsyncSession,
) -> None:
    """The 403 response itself is an "error" as far as the request pipeline
    is concerned — this proves that doesn't roll back the audit write
    require_owner already committed (the bug commit-before-raise exists to
    prevent)."""
    login = await client.post(
        "/auth/login",
        json={"email": "manager@test.lk", "password": manager_password, "device_id": "d1"},
    )
    token = login.json()["access_token"]

    # POST /users with an owner-only 403 AND a body that would also fail
    # validation if it ever reached the handler — the denial must still be
    # audited regardless.
    resp = await client.post(
        "/users", json={}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403

    count = (
        await session.execute(
            text(
                "SELECT count(*) FROM audit_logs "
                "WHERE company_id = :cid AND action = 'PERMISSION_DENIED'"
            ),
            {"cid": str(company)},
        )
    ).scalar_one()
    assert count == 1
