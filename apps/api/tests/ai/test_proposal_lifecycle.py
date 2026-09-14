"""P8 Lite Slice 5 — cancel and lazy expiry (`app/ai/proposals.py`).

Cancel never touches business data; it only ever moves an `AiProposal`
between its own states. Expiry has no scheduler — whichever call happens
to touch a `PENDING` proposal past its `expires_at` is what discovers and
persists the `EXPIRED` transition.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.proposals import cancel_proposal
from app.core.context import SecurityContext
from app.core.dates import now_utc
from app.core.errors import ConflictError, NotFoundError, ProposalExpiredError
from app.models.user import UserRole


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


@pytest.fixture
def owner_ctx(owner: uuid.UUID, company: uuid.UUID) -> SecurityContext:
    return SecurityContext(user_id=owner, company_id=company, role=UserRole.OWNER, store_ids=())


@pytest.fixture
async def ai_session_id(session: AsyncSession, company: uuid.UUID, owner: uuid.UUID) -> uuid.UUID:
    ai_session_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO ai_sessions (id, company_id, user_id) VALUES (:id, :cid, :uid)"),
        {"id": str(ai_session_id), "cid": str(company), "uid": str(owner)},
    )
    await session.commit()
    return ai_session_id


async def _insert_proposal(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    ai_session_id: uuid.UUID,
    owner: uuid.UUID,
    status: str = "PENDING",
    expires_in_minutes: int = 10,
) -> uuid.UUID:
    proposal_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO ai_proposals "
            "(id, company_id, session_id, created_by, summary, status, expires_at) "
            "VALUES (:id, :cid, :sid, :owner, 'Test proposal', :status, :expires_at)"
        ),
        {
            "id": str(proposal_id),
            "cid": str(company_id),
            "sid": str(ai_session_id),
            "owner": str(owner),
            "status": status,
            "expires_at": now_utc() + timedelta(minutes=expires_in_minutes),
        },
    )
    await session.commit()
    return proposal_id


class TestCancelProposal:
    async def test_pending_becomes_cancelled(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        company: uuid.UUID,
        ai_session_id: uuid.UUID,
        owner: uuid.UUID,
    ) -> None:
        proposal_id = await _insert_proposal(
            session, company_id=company, ai_session_id=ai_session_id, owner=owner
        )

        proposal = await cancel_proposal(session, owner_ctx, proposal_id)

        assert proposal.status.value == "CANCELLED"

    async def test_cancelling_twice_is_safe(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        company: uuid.UUID,
        ai_session_id: uuid.UUID,
        owner: uuid.UUID,
    ) -> None:
        proposal_id = await _insert_proposal(
            session, company_id=company, ai_session_id=ai_session_id, owner=owner
        )

        first = await cancel_proposal(session, owner_ctx, proposal_id)
        second = await cancel_proposal(session, owner_ctx, proposal_id)

        assert first.status.value == "CANCELLED"
        assert second.status.value == "CANCELLED"

    async def test_cancelling_an_applied_proposal_is_conflict(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        company: uuid.UUID,
        ai_session_id: uuid.UUID,
        owner: uuid.UUID,
    ) -> None:
        proposal_id = await _insert_proposal(
            session, company_id=company, ai_session_id=ai_session_id, owner=owner, status="APPLIED"
        )

        with pytest.raises(ConflictError):
            await cancel_proposal(session, owner_ctx, proposal_id)

    async def test_an_expired_pending_proposal_is_discovered_and_marked_expired(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        company: uuid.UUID,
        ai_session_id: uuid.UUID,
        owner: uuid.UUID,
    ) -> None:
        proposal_id = await _insert_proposal(
            session,
            company_id=company,
            ai_session_id=ai_session_id,
            owner=owner,
            expires_in_minutes=-1,
        )

        with pytest.raises(ProposalExpiredError):
            await cancel_proposal(session, owner_ctx, proposal_id)
        await session.commit()

        row = (
            await session.execute(
                text("SELECT status FROM ai_proposals WHERE id = :id"), {"id": str(proposal_id)}
            )
        ).one()
        assert row.status == "EXPIRED"

    async def test_cross_tenant_proposal_is_not_found(
        self, session: AsyncSession, owner_ctx: SecurityContext
    ) -> None:
        with pytest.raises(NotFoundError):
            await cancel_proposal(session, owner_ctx, uuid.uuid4())

    async def test_cancel_never_touches_business_data(
        self,
        client: AsyncClient,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        company: uuid.UUID,
        ai_session_id: uuid.UUID,
        owner: uuid.UUID,
        owner_password: str,
    ) -> None:
        from app.ai.tools.propose_tools import ProposeUpdateParams, propose_update

        headers = await _owner_headers(client, owner_password)
        page_resp = await client.post(
            "/pages",
            json={"name": "Notes", "columns": [{"name": "Text", "data_type": "TEXT"}]},
            headers=headers,
        )
        assert page_resp.status_code == 201, page_resp.text
        page = page_resp.json()
        record_resp = await client.post(
            f"/pages/{page['id']}/records",
            json={"occurred_at": "2026-01-05T09:00:00Z", "data": {"text": "original"}},
            headers=headers,
        )
        assert record_resp.status_code == 201, record_resp.text
        record = record_resp.json()

        result = await propose_update(
            ctx=owner_ctx,
            session=session,
            ai_session_id=ai_session_id,
            params=ProposeUpdateParams(
                page_key="notes", record_id=record["id"], changes={"text": "changed"}
            ),
        )
        await session.commit()

        await cancel_proposal(session, owner_ctx, uuid.UUID(result["proposal_id"]))
        await session.commit()

        row = (
            await session.execute(
                text("SELECT data FROM records WHERE id = :id"), {"id": record["id"]}
            )
        ).one()
        assert row.data["text"] == "original"


class TestCancelEndpoint:
    async def test_owner_can_cancel_via_http(
        self,
        client: AsyncClient,
        session: AsyncSession,
        company: uuid.UUID,
        ai_session_id: uuid.UUID,
        owner: uuid.UUID,
        owner_password: str,
    ) -> None:
        proposal_id = await _insert_proposal(
            session, company_id=company, ai_session_id=ai_session_id, owner=owner
        )
        headers = await _owner_headers(client, owner_password)

        resp = await client.post(f"/ai/proposals/{proposal_id}/cancel", headers=headers)

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "CANCELLED"

    async def test_manager_is_blocked(
        self,
        client: AsyncClient,
        session: AsyncSession,
        company: uuid.UUID,
        ai_session_id: uuid.UUID,
        owner: uuid.UUID,
        manager: uuid.UUID,
        manager_password: str,
    ) -> None:
        proposal_id = await _insert_proposal(
            session, company_id=company, ai_session_id=ai_session_id, owner=owner
        )
        headers = await _manager_headers(client, manager_password)

        resp = await client.post(f"/ai/proposals/{proposal_id}/cancel", headers=headers)

        assert resp.status_code == 403
        assert resp.json()["code"] == "PERMISSION_DENIED"
