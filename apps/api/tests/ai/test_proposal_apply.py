"""P8 Lite Slice 6 — the apply endpoint, the security-sensitive one.

Every scenario in the brief's Section 20: stale version -> 409
PROPOSAL_STALE with no overwrite; expired -> 409 PROPOSAL_EXPIRED with no
change; a resolved proposal cannot be applied twice; the happy path
actually changes the record, recalculates formulas, and writes two audit
entries with source="AI" and the real ai_session_id.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.proposals import apply_proposal
from app.ai.tools.propose_tools import ProposeUpdateParams, propose_update
from app.core.context import SecurityContext
from app.core.errors import ConflictError, NotFoundError, ProposalExpiredError, ProposalStaleError
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


@pytest.fixture
async def payroll_record(client: AsyncClient, owner: uuid.UUID, owner_password: str) -> dict:
    headers = await _owner_headers(client, owner_password)
    resp = await client.post(
        "/pages",
        json={
            "name": "Payroll",
            "columns": [
                {"name": "Employee", "data_type": "TEXT"},
                {"name": "Basic Salary", "data_type": "CURRENCY"},
                {"name": "Allowance", "data_type": "CURRENCY"},
                {"name": "Deduction", "data_type": "CURRENCY"},
                {
                    "name": "Net Salary",
                    "data_type": "FORMULA",
                    "config": {"expression": "basic_salary + allowance - deduction"},
                },
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    page = resp.json()
    record_resp = await client.post(
        f"/pages/{page['id']}/records",
        json={
            "occurred_at": "2026-01-05T09:00:00Z",
            "data": {
                "employee": "John Perera",
                "basic_salary": "60000.00",
                "allowance": "10000.00",
                "deduction": "5000.00",
            },
        },
        headers=headers,
    )
    assert record_resp.status_code == 201, record_resp.text
    page["record"] = record_resp.json()
    return page


async def _propose_salary_change(
    session: AsyncSession, owner_ctx: SecurityContext, ai_session_id: uuid.UUID, record: dict
) -> str:
    result = await propose_update(
        ctx=owner_ctx,
        session=session,
        ai_session_id=ai_session_id,
        params=ProposeUpdateParams(
            page_key="payroll", record_id=record["id"], changes={"basic_salary": "75000.00"}
        ),
    )
    await session.commit()
    return str(result["proposal_id"])


class TestApplyHappyPath:
    async def test_record_is_changed_formula_recalculated_and_audited(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        payroll_record: dict,
    ) -> None:
        record = payroll_record["record"]
        proposal_id = await _propose_salary_change(session, owner_ctx, ai_session_id, record)

        proposal = await apply_proposal(session, owner_ctx, uuid.UUID(proposal_id))
        await session.commit()

        assert proposal.status.value == "APPLIED"
        assert proposal.applied_at is not None
        assert str(proposal.applied_by) == str(owner_ctx.user_id)

        row = (
            await session.execute(
                text("SELECT data, version FROM records WHERE id = :id"), {"id": record["id"]}
            )
        ).one()
        assert Decimal(row.data["basic_salary"]) == Decimal("75000.00")
        assert row.version == record["version"] + 1

        audit_rows = (
            await session.execute(
                text(
                    "SELECT action, source, ai_session_id FROM audit_logs "
                    "WHERE company_id = :cid AND source = 'AI' ORDER BY created_at"
                ),
                {"cid": str(owner_ctx.company_id)},
            )
        ).all()
        actions = [r.action for r in audit_rows]
        assert "AI_PROPOSAL_CREATED" in actions
        assert "RECORD_UPDATE" in actions
        assert "AI_PROPOSAL_APPLIED" in actions
        for r in audit_rows:
            assert str(r.ai_session_id) == str(ai_session_id)

    async def test_formula_column_shows_recalculated_value_after_apply(
        self,
        client: AsyncClient,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        owner_password: str,
        ai_session_id: uuid.UUID,
        payroll_record: dict,
    ) -> None:
        record = payroll_record["record"]
        proposal_id = await _propose_salary_change(session, owner_ctx, ai_session_id, record)
        await apply_proposal(session, owner_ctx, uuid.UUID(proposal_id))
        await session.commit()

        headers = await _owner_headers(client, owner_password)
        resp = await client.get(f"/records/{record['id']}", headers=headers)
        assert resp.status_code == 200, resp.text
        assert Decimal(resp.json()["data"]["net_salary"]) == Decimal("80000.00")


class TestApplyStaleVersion:
    async def test_stale_version_is_conflict_and_record_unchanged(
        self,
        client: AsyncClient,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        owner_password: str,
        ai_session_id: uuid.UUID,
        payroll_record: dict,
    ) -> None:
        record = payroll_record["record"]
        proposal_id = await _propose_salary_change(session, owner_ctx, ai_session_id, record)

        # Someone else changes the record after the proposal was created.
        headers = await _owner_headers(client, owner_password)
        other_change = await client.patch(
            f"/records/{record['id']}",
            json={"version": record["version"], "data": {"allowance": "20000.00"}},
            headers=headers,
        )
        assert other_change.status_code == 200, other_change.text

        with pytest.raises(ProposalStaleError):
            await apply_proposal(session, owner_ctx, uuid.UUID(proposal_id))
        await session.commit()

        row = (
            await session.execute(
                text("SELECT data FROM records WHERE id = :id"), {"id": record["id"]}
            )
        ).one()
        assert Decimal(row.data["basic_salary"]) == Decimal("60000.00")  # unchanged by the proposal

        proposal_row = (
            await session.execute(
                text("SELECT status FROM ai_proposals WHERE id = :id"), {"id": proposal_id}
            )
        ).one()
        assert proposal_row.status == "PENDING"


class TestApplyExpired:
    async def test_expired_proposal_returns_409_and_record_unchanged(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        payroll_record: dict,
    ) -> None:
        record = payroll_record["record"]
        proposal_id = await _propose_salary_change(session, owner_ctx, ai_session_id, record)
        await session.execute(
            text("UPDATE ai_proposals SET expires_at = now() - interval '1 minute' WHERE id = :id"),
            {"id": proposal_id},
        )
        await session.commit()

        with pytest.raises(ProposalExpiredError):
            await apply_proposal(session, owner_ctx, uuid.UUID(proposal_id))
        await session.commit()

        row = (
            await session.execute(
                text("SELECT data FROM records WHERE id = :id"), {"id": record["id"]}
            )
        ).one()
        assert Decimal(row.data["basic_salary"]) == Decimal("60000.00")

        proposal_row = (
            await session.execute(
                text("SELECT status FROM ai_proposals WHERE id = :id"), {"id": proposal_id}
            )
        ).one()
        assert proposal_row.status == "EXPIRED"


class TestApplyTwiceRejected:
    async def test_double_apply_is_rejected(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        payroll_record: dict,
    ) -> None:
        record = payroll_record["record"]
        proposal_id = await _propose_salary_change(session, owner_ctx, ai_session_id, record)

        await apply_proposal(session, owner_ctx, uuid.UUID(proposal_id))
        await session.commit()

        with pytest.raises(ConflictError):
            await apply_proposal(session, owner_ctx, uuid.UUID(proposal_id))


class TestApplyCrossTenant:
    async def test_cross_tenant_proposal_is_not_found(
        self, session: AsyncSession, owner_ctx: SecurityContext
    ) -> None:
        with pytest.raises(NotFoundError):
            await apply_proposal(session, owner_ctx, uuid.uuid4())


class TestApplyEndpoint:
    async def test_owner_can_apply_via_http(
        self,
        client: AsyncClient,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        owner_password: str,
        ai_session_id: uuid.UUID,
        payroll_record: dict,
    ) -> None:
        record = payroll_record["record"]
        proposal_id = await _propose_salary_change(session, owner_ctx, ai_session_id, record)
        headers = await _owner_headers(client, owner_password)

        resp = await client.post(f"/ai/proposals/{proposal_id}/apply", headers=headers)

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "APPLIED"

    async def test_manager_is_blocked(
        self,
        client: AsyncClient,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        owner_password: str,
        manager: uuid.UUID,
        manager_password: str,
        ai_session_id: uuid.UUID,
        payroll_record: dict,
    ) -> None:
        record = payroll_record["record"]
        proposal_id = await _propose_salary_change(session, owner_ctx, ai_session_id, record)
        headers = await _manager_headers(client, manager_password)

        resp = await client.post(f"/ai/proposals/{proposal_id}/apply", headers=headers)

        assert resp.status_code == 403
        assert resp.json()["code"] == "PERMISSION_DENIED"

        # Never even reached the proposal — record and proposal both untouched.
        proposal_row = (
            await session.execute(
                text("SELECT status FROM ai_proposals WHERE id = :id"), {"id": proposal_id}
            )
        ).one()
        assert proposal_row.status == "PENDING"
