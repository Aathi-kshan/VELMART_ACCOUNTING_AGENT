"""A manager gets 403 on every `/ai/*` endpoint, at the router layer,
before any orchestrator/model/DB work happens — and each denial is
audited via `require_owner`'s existing PERMISSION_DENIED write (plan
sections 16.2, 18.2, 20.2). Extended in P8 Lite for the two proposal
routes: a manager can neither apply nor cancel a proposal, and the
proposal itself is left completely untouched by the attempt.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _manager_token(client: AsyncClient, manager_password: str) -> str:
    resp = await client.post(
        "/auth/login",
        json={"email": "manager@test.lk", "password": manager_password, "device_id": "d1"},
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


async def test_manager_cannot_create_an_ai_session(
    client: AsyncClient, manager: uuid.UUID, manager_password: str, company: uuid.UUID
) -> None:
    token = await _manager_token(client, manager_password)

    resp = await client.post("/ai/sessions", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 403
    assert resp.json()["code"] == "PERMISSION_DENIED"


async def test_manager_cannot_send_an_ai_message(
    client: AsyncClient,
    manager: uuid.UUID,
    manager_password: str,
    company: uuid.UUID,
    session: AsyncSession,
    owner: uuid.UUID,
) -> None:
    token = await _manager_token(client, manager_password)

    # A real session id (owned by the Owner) — proves the 403 comes from the
    # Owner-only guard itself, not from a 404 on a made-up id.
    ai_session_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO ai_sessions (id, company_id, user_id) VALUES (:id, :company_id, :owner)"),
        {"id": str(ai_session_id), "company_id": str(company), "owner": str(owner)},
    )
    await session.commit()

    resp = await client.post(
        f"/ai/sessions/{ai_session_id}/messages",
        json={"message": "How much did we spend last month?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 403
    assert resp.json()["code"] == "PERMISSION_DENIED"


async def test_manager_denials_on_ai_endpoints_are_audited(
    client: AsyncClient,
    manager: uuid.UUID,
    manager_password: str,
    company: uuid.UUID,
    session: AsyncSession,
) -> None:
    token = await _manager_token(client, manager_password)

    resp = await client.post("/ai/sessions", headers={"Authorization": f"Bearer {token}"})
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


async def _insert_pending_proposal(
    session: AsyncSession, *, company: uuid.UUID, owner: uuid.UUID
) -> uuid.UUID:
    ai_session_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO ai_sessions (id, company_id, user_id) VALUES (:id, :cid, :uid)"),
        {"id": str(ai_session_id), "cid": str(company), "uid": str(owner)},
    )
    proposal_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO ai_proposals "
            "(id, company_id, session_id, created_by, summary, status, expires_at) "
            "VALUES (:id, :cid, :sid, :owner, 'Test proposal', 'PENDING', "
            "now() + interval '10 minutes')"
        ),
        {
            "id": str(proposal_id),
            "cid": str(company),
            "sid": str(ai_session_id),
            "owner": str(owner),
        },
    )
    await session.commit()
    return proposal_id


async def test_manager_cannot_apply_a_proposal(
    client: AsyncClient,
    manager: uuid.UUID,
    manager_password: str,
    company: uuid.UUID,
    session: AsyncSession,
    owner: uuid.UUID,
) -> None:
    proposal_id = await _insert_pending_proposal(session, company=company, owner=owner)
    token = await _manager_token(client, manager_password)

    resp = await client.post(
        f"/ai/proposals/{proposal_id}/apply", headers={"Authorization": f"Bearer {token}"}
    )

    assert resp.status_code == 403
    assert resp.json()["code"] == "PERMISSION_DENIED"

    row = (
        await session.execute(
            text("SELECT status FROM ai_proposals WHERE id = :id"), {"id": str(proposal_id)}
        )
    ).one()
    assert row.status == "PENDING"


async def test_manager_cannot_cancel_a_proposal(
    client: AsyncClient,
    manager: uuid.UUID,
    manager_password: str,
    company: uuid.UUID,
    session: AsyncSession,
    owner: uuid.UUID,
) -> None:
    proposal_id = await _insert_pending_proposal(session, company=company, owner=owner)
    token = await _manager_token(client, manager_password)

    resp = await client.post(
        f"/ai/proposals/{proposal_id}/cancel", headers={"Authorization": f"Bearer {token}"}
    )

    assert resp.status_code == 403
    assert resp.json()["code"] == "PERMISSION_DENIED"

    row = (
        await session.execute(
            text("SELECT status FROM ai_proposals WHERE id = :id"), {"id": str(proposal_id)}
        )
    ).one()
    assert row.status == "PENDING"


async def test_manager_proposal_denials_are_audited(
    client: AsyncClient,
    manager: uuid.UUID,
    manager_password: str,
    company: uuid.UUID,
    session: AsyncSession,
    owner: uuid.UUID,
) -> None:
    proposal_id = await _insert_pending_proposal(session, company=company, owner=owner)
    token = await _manager_token(client, manager_password)

    resp = await client.post(
        f"/ai/proposals/{proposal_id}/apply", headers={"Authorization": f"Bearer {token}"}
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


async def test_owner_can_create_an_ai_session(
    client: AsyncClient, owner: uuid.UUID, owner_password: str
) -> None:
    login = await client.post(
        "/auth/login",
        json={"email": "owner@test.lk", "password": owner_password, "device_id": "d1"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    resp = await client.post("/ai/sessions", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 201, resp.text
    assert "id" in resp.json()
