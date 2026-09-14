"""P8 Lite Slice 9 — the behavioral proof the brief explicitly asks for:
"no AI-exposed tool can directly mutate business data." Rather than a
per-tool test asserting this by inspection (already true, and already
covered by each tool's own test file), this walks the real
`TOOL_REGISTRY`, calls every `kind="propose"` tool found there, and
asserts the target row is byte-for-byte identical afterward — so a future
propose tool that forgets this guarantee fails here even before its own
tests are written.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.propose_tools import ProposeStatusChangeParams, ProposeUpdateParams
from app.ai.tools.registry import TOOL_REGISTRY
from app.core.context import SecurityContext
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
async def staff_record(client: AsyncClient, owner: uuid.UUID, owner_password: str) -> dict:
    headers = await _owner_headers(client, owner_password)
    page_resp = await client.post(
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
    assert page_resp.status_code == 201, page_resp.text
    page = page_resp.json()
    record_resp = await client.post(
        f"/pages/{page['id']}/records",
        json={
            "occurred_at": "2026-01-05T09:00:00Z",
            "data": {"employee": "John Perera", "salary": "60000.00"},
        },
        headers=headers,
    )
    assert record_resp.status_code == 201, record_resp.text
    return record_resp.json()


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


async def _call_propose_update(
    ctx: SecurityContext, session: AsyncSession, ai_session_id: uuid.UUID, record: dict
) -> dict[str, Any]:
    from app.ai.tools.propose_tools import propose_update

    return await propose_update(
        ctx=ctx,
        session=session,
        ai_session_id=ai_session_id,
        params=ProposeUpdateParams(
            page_key="staff", record_id=record["id"], changes={"salary": "99999.00"}
        ),
    )


async def _call_propose_status_change(
    ctx: SecurityContext, session: AsyncSession, ai_session_id: uuid.UUID, record: dict
) -> dict[str, Any]:
    from app.ai.tools.propose_tools import propose_status_change

    return await propose_status_change(
        ctx=ctx,
        session=session,
        ai_session_id=ai_session_id,
        params=ProposeStatusChangeParams(
            page_key="cheques", record_id=record["id"], column_key="cheque_status", value="PAID"
        ),
    )


class TestNoProposeToolDirectlyMutatesBusinessData:
    def test_every_propose_tool_is_covered_by_this_file(self) -> None:
        propose_tool_names = {t.name for t in TOOL_REGISTRY.values() if t.kind == "propose"}
        assert propose_tool_names == {"propose_update", "propose_status_change"}, (
            "A propose tool was added/removed without updating this test's coverage — "
            f"registry has {propose_tool_names}."
        )

    async def test_propose_update_leaves_the_records_row_byte_for_byte_unchanged(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        staff_record: dict,
    ) -> None:
        before = (
            (
                await session.execute(
                    text("SELECT * FROM records WHERE id = :id"), {"id": staff_record["id"]}
                )
            )
            .mappings()
            .one()
        )

        result = await _call_propose_update(owner_ctx, session, ai_session_id, staff_record)
        assert "error" not in result

        after = (
            (
                await session.execute(
                    text("SELECT * FROM records WHERE id = :id"), {"id": staff_record["id"]}
                )
            )
            .mappings()
            .one()
        )
        assert dict(before) == dict(after)

    async def test_propose_status_change_leaves_the_cheques_row_byte_for_byte_unchanged(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        cheque_record: dict,
    ) -> None:
        before = (
            (
                await session.execute(
                    text("SELECT * FROM cheques WHERE id = :id"), {"id": cheque_record["id"]}
                )
            )
            .mappings()
            .one()
        )

        result = await _call_propose_status_change(owner_ctx, session, ai_session_id, cheque_record)
        assert "error" not in result

        after = (
            (
                await session.execute(
                    text("SELECT * FROM cheques WHERE id = :id"), {"id": cheque_record["id"]}
                )
            )
            .mappings()
            .one()
        )
        assert dict(before) == dict(after)

    async def test_only_ai_proposal_tables_gain_rows_across_every_propose_tool(
        self,
        session: AsyncSession,
        owner_ctx: SecurityContext,
        ai_session_id: uuid.UUID,
        staff_record: dict,
        cheque_record: dict,
    ) -> None:
        before_counts = {
            table: (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()  # noqa: S608
            for table in ("records", "cheques", "ai_proposals", "ai_proposal_items")
        }

        await _call_propose_update(owner_ctx, session, ai_session_id, staff_record)
        await _call_propose_status_change(owner_ctx, session, ai_session_id, cheque_record)

        after_counts = {
            table: (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()  # noqa: S608
            for table in ("records", "cheques", "ai_proposals", "ai_proposal_items")
        }

        assert after_counts["records"] == before_counts["records"]
        assert after_counts["cheques"] == before_counts["cheques"]
        assert after_counts["ai_proposals"] == before_counts["ai_proposals"] + 2
        assert after_counts["ai_proposal_items"] == before_counts["ai_proposal_items"] + 2
