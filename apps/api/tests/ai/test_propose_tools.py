"""P8 Lite Slice 2/3 — propose_update and propose_status_change.

Every test here proves the same thing from a different angle: a propose
tool call produces a PENDING AiProposal/AiProposalItem while the target
business record is completely untouched — `before_data` always comes from
the database, never from what the model claims.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.propose_tools import (
    ProposeStatusChangeParams,
    ProposeUpdateParams,
    propose_status_change,
    propose_update,
)
from app.core.context import SecurityContext
from app.core.errors import NotFoundError, ValidationFailedError
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
async def staff_page(client: AsyncClient, owner: uuid.UUID, owner_password: str) -> dict:
    headers = await _owner_headers(client, owner_password)
    resp = await client.post(
        "/pages",
        json={
            "name": "Staff",
            "columns": [
                {"name": "Employee", "data_type": "TEXT"},
                {"name": "Salary", "data_type": "CURRENCY"},
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
            "data": {"employee": "John Perera", "salary": "60000.00"},
        },
        headers=headers,
    )
    assert record_resp.status_code == 201, record_resp.text
    page["record"] = record_resp.json()
    return page


async def _proposal_row(session: AsyncSession, proposal_id: str) -> object:
    return (
        await session.execute(
            text("SELECT status, expires_at, session_id FROM ai_proposals WHERE id = :id"),
            {"id": proposal_id},
        )
    ).one()


async def _proposal_item_row(session: AsyncSession, proposal_id: str) -> object:
    return (
        await session.execute(
            text(
                "SELECT operation, record_id, expected_version, before_data, after_data "
                "FROM ai_proposal_items WHERE proposal_id = :id"
            ),
            {"id": proposal_id},
        )
    ).one()


class TestProposeUpdateCreatesAPendingProposal:
    async def test_target_record_is_untouched(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        staff_page: dict,
    ) -> None:
        record = staff_page["record"]

        result = await propose_update(
            ctx=owner_ctx,
            session=session,
            ai_session_id=ai_session_id,
            params=ProposeUpdateParams(
                page_key="staff", record_id=record["id"], changes={"salary": "75000.00"}
            ),
        )

        proposal = await _proposal_row(session, result["proposal_id"])
        assert proposal.status == "PENDING"
        item = await _proposal_item_row(session, result["proposal_id"])
        assert item.operation == "UPDATE"
        assert item.expected_version == record["version"]

        # The record itself is provably untouched.
        row = (
            await session.execute(
                text("SELECT data, version FROM records WHERE id = :id"), {"id": record["id"]}
            )
        ).one()
        assert row.data["salary"] == "60000.00"
        assert row.version == record["version"]

    async def test_before_data_comes_from_the_database_not_the_ai(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        staff_page: dict,
    ) -> None:
        """Even if the model's implicit "current value" were wrong, the
        proposal's before_data must still match what is actually stored."""
        record = staff_page["record"]

        result = await propose_update(
            ctx=owner_ctx,
            session=session,
            ai_session_id=ai_session_id,
            params=ProposeUpdateParams(
                page_key="staff", record_id=record["id"], changes={"salary": "75000.00"}
            ),
        )

        assert Decimal(result["before"]["salary"]) == Decimal("60000.00")
        assert Decimal(result["after"]["salary"]) == Decimal("75000.00")

        item = await _proposal_item_row(session, result["proposal_id"])
        assert Decimal(item.before_data["salary"]) == Decimal("60000.00")
        assert Decimal(item.after_data["salary"]) == Decimal("75000.00")

    async def test_only_proposal_tables_gain_rows(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        staff_page: dict,
    ) -> None:
        record = staff_page["record"]
        before_count = (await session.execute(text("SELECT count(*) FROM records"))).scalar_one()

        await propose_update(
            ctx=owner_ctx,
            session=session,
            ai_session_id=ai_session_id,
            params=ProposeUpdateParams(
                page_key="staff", record_id=record["id"], changes={"salary": "75000.00"}
            ),
        )

        after_count = (await session.execute(text("SELECT count(*) FROM records"))).scalar_one()
        assert after_count == before_count


class TestProposeUpdateRejections:
    async def test_invalid_column_is_rejected(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        staff_page: dict,
    ) -> None:
        record = staff_page["record"]
        with pytest.raises(ValidationFailedError):
            await propose_update(
                ctx=owner_ctx,
                session=session,
                ai_session_id=ai_session_id,
                params=ProposeUpdateParams(
                    page_key="staff", record_id=record["id"], changes={"not_a_column": "x"}
                ),
            )

    async def test_invalid_value_type_is_rejected(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        staff_page: dict,
    ) -> None:
        record = staff_page["record"]
        with pytest.raises(ValidationFailedError):
            await propose_update(
                ctx=owner_ctx,
                session=session,
                ai_session_id=ai_session_id,
                params=ProposeUpdateParams(
                    page_key="staff", record_id=record["id"], changes={"salary": "not-a-number"}
                ),
            )

    async def test_nonexistent_record_id_is_not_found(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        staff_page: dict,
    ) -> None:
        with pytest.raises(NotFoundError):
            await propose_update(
                ctx=owner_ctx,
                session=session,
                ai_session_id=ai_session_id,
                params=ProposeUpdateParams(
                    page_key="staff", record_id=str(uuid.uuid4()), changes={"salary": "1.00"}
                ),
            )

    async def test_malformed_record_id_is_rejected(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        staff_page: dict,
    ) -> None:
        with pytest.raises(ValidationFailedError):
            await propose_update(
                ctx=owner_ctx,
                session=session,
                ai_session_id=ai_session_id,
                params=ProposeUpdateParams(
                    page_key="staff", record_id="not-a-uuid", changes={"salary": "1.00"}
                ),
            )

    async def test_wrong_company_record_is_not_found(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        staff_page: dict,
    ) -> None:
        other_company_id = uuid.uuid4()
        await session.execute(
            text("INSERT INTO companies (id, name) VALUES (:id, 'Other Co')"),
            {"id": str(other_company_id)},
        )
        await session.commit()
        other_ctx = SecurityContext(
            user_id=uuid.uuid4(), company_id=other_company_id, role=UserRole.OWNER, store_ids=()
        )

        with pytest.raises(NotFoundError):
            await propose_update(
                ctx=other_ctx,
                session=session,
                ai_session_id=ai_session_id,
                params=ProposeUpdateParams(
                    page_key="staff",
                    record_id=staff_page["record"]["id"],
                    changes={"salary": "1.00"},
                ),
            )

    async def test_wrong_page_is_not_found(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        staff_page: dict,
        system_page_ids: dict[str, str],
    ) -> None:
        with pytest.raises(NotFoundError):
            await propose_update(
                ctx=owner_ctx,
                session=session,
                ai_session_id=ai_session_id,
                params=ProposeUpdateParams(
                    page_key="expenses",
                    record_id=staff_page["record"]["id"],
                    changes={"amount": "1.00"},
                ),
            )

    async def test_no_such_page_is_not_found(
        self, session: AsyncSession, owner_ctx: SecurityContext, ai_session_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await propose_update(
                ctx=owner_ctx,
                session=session,
                ai_session_id=ai_session_id,
                params=ProposeUpdateParams(
                    page_key="no_such_page", record_id=str(uuid.uuid4()), changes={"x": "1"}
                ),
            )

    async def test_protected_column_change_points_to_propose_status_change(
        self,
        client: AsyncClient,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        owner_password: str,
        ai_session_id: uuid.UUID,
        system_page_ids: dict[str, str],
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        record_resp = await client.post(
            f"/pages/{system_page_ids['cheques']}/records",
            json={
                "occurred_at": "2026-01-05T09:00:00Z",
                "data": {"cheque_number": "CHQ-1", "amount": "1000.00"},
            },
            headers=headers,
        )
        assert record_resp.status_code == 201, record_resp.text
        record = record_resp.json()

        with pytest.raises(ValidationFailedError, match="propose_status_change"):
            await propose_update(
                ctx=owner_ctx,
                session=session,
                ai_session_id=ai_session_id,
                params=ProposeUpdateParams(
                    page_key="cheques",
                    record_id=record["id"],
                    changes={"cheque_status": "PAID"},
                ),
            )

    async def test_ledger_page_is_rejected(
        self,
        client: AsyncClient,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        owner_password: str,
        ai_session_id: uuid.UUID,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_resp = await client.post(
            "/pages",
            json={
                "name": "Loan Ledger",
                "kind": "LEDGER",
                "columns": [{"name": "Amount", "data_type": "CURRENCY"}],
            },
            headers=headers,
        )
        assert page_resp.status_code == 201, page_resp.text
        page = page_resp.json()
        record_resp = await client.post(
            f"/pages/{page['id']}/records",
            json={"occurred_at": "2026-01-05T09:00:00Z", "data": {"amount": "1000.00"}},
            headers=headers,
        )
        assert record_resp.status_code == 201, record_resp.text
        record = record_resp.json()

        with pytest.raises(ValidationFailedError):
            await propose_update(
                ctx=owner_ctx,
                session=session,
                ai_session_id=ai_session_id,
                params=ProposeUpdateParams(
                    page_key="loan_ledger", record_id=record["id"], changes={"amount": "2000.00"}
                ),
            )


@pytest.fixture
async def cheque_record(
    client: AsyncClient, owner_password: str, system_page_ids: dict[str, str]
) -> dict:
    headers = await _owner_headers(client, owner_password)
    resp = await client.post(
        f"/pages/{system_page_ids['cheques']}/records",
        json={
            "occurred_at": "2026-01-05T09:00:00Z",
            "data": {"cheque_number": "CHQ-1", "amount": "1000.00"},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestProposeStatusChangeCreatesAPendingProposal:
    async def test_target_record_is_untouched(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        cheque_record: dict,
    ) -> None:
        result = await propose_status_change(
            ctx=owner_ctx,
            session=session,
            ai_session_id=ai_session_id,
            params=ProposeStatusChangeParams(
                page_key="cheques",
                record_id=cheque_record["id"],
                column_key="cheque_status",
                value="PAID",
            ),
        )

        proposal = await _proposal_row(session, result["proposal_id"])
        assert proposal.status == "PENDING"
        item = await _proposal_item_row(session, result["proposal_id"])
        assert item.operation == "STATUS_CHANGE"
        assert item.expected_version == cheque_record["version"]

        row = (
            await session.execute(
                text("SELECT cheque_status, version FROM cheques WHERE id = :id"),
                {"id": cheque_record["id"]},
            )
        ).one()
        assert row.cheque_status == "PENDING"
        assert row.version == cheque_record["version"]

    async def test_before_and_after_reflect_the_real_status(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        cheque_record: dict,
    ) -> None:
        result = await propose_status_change(
            ctx=owner_ctx,
            session=session,
            ai_session_id=ai_session_id,
            params=ProposeStatusChangeParams(
                page_key="cheques",
                record_id=cheque_record["id"],
                column_key="cheque_status",
                value="PAID",
            ),
        )

        assert result["before"]["cheque_status"] == "PENDING"
        assert result["after"]["cheque_status"] == "PAID"


class TestProposeStatusChangeRejections:
    async def test_non_protected_column_is_rejected(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        cheque_record: dict,
    ) -> None:
        with pytest.raises(ValidationFailedError):
            await propose_status_change(
                ctx=owner_ctx,
                session=session,
                ai_session_id=ai_session_id,
                params=ProposeStatusChangeParams(
                    page_key="cheques",
                    record_id=cheque_record["id"],
                    column_key="payee_name",
                    value="Someone",
                ),
            )

    async def test_out_of_options_value_is_rejected(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        cheque_record: dict,
    ) -> None:
        with pytest.raises(ValidationFailedError):
            await propose_status_change(
                ctx=owner_ctx,
                session=session,
                ai_session_id=ai_session_id,
                params=ProposeStatusChangeParams(
                    page_key="cheques",
                    record_id=cheque_record["id"],
                    column_key="cheque_status",
                    value="CANCELLED",
                ),
            )

    async def test_nonexistent_record_is_not_found(
        self, session: AsyncSession, owner_ctx: SecurityContext, ai_session_id: uuid.UUID
    ) -> None:
        with pytest.raises(NotFoundError):
            await propose_status_change(
                ctx=owner_ctx,
                session=session,
                ai_session_id=ai_session_id,
                params=ProposeStatusChangeParams(
                    page_key="cheques",
                    record_id=str(uuid.uuid4()),
                    column_key="cheque_status",
                    value="PAID",
                ),
            )


class TestFormulaImpact:
    """Slice 4 — a proposal on a page with a FORMULA column shows the
    correctly recalculated downstream value, using the same
    `formula_service.apply_formulas` every real read/update already uses —
    no new formula code."""

    @pytest.fixture
    async def payroll_page(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> dict:
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

    async def test_before_and_after_show_the_recalculated_formula(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        payroll_page: dict,
    ) -> None:
        record = payroll_page["record"]
        assert Decimal(record["data"]["net_salary"]) == Decimal("65000.00")

        result = await propose_update(
            ctx=owner_ctx,
            session=session,
            ai_session_id=ai_session_id,
            params=ProposeUpdateParams(
                page_key="payroll", record_id=record["id"], changes={"basic_salary": "75000.00"}
            ),
        )

        assert Decimal(result["before"]["net_salary"]) == Decimal("65000.00")
        assert Decimal(result["after"]["net_salary"]) == Decimal("80000.00")

        item = await _proposal_item_row(session, result["proposal_id"])
        assert Decimal(item.before_data["net_salary"]) == Decimal("65000.00")
        assert Decimal(item.after_data["net_salary"]) == Decimal("80000.00")
