"""P8 Lite Slice 1 — the plumbing every later proposal slice needs:
`write_audit_log` can attribute an entry to an AI session, and
`record_service.update_record`/`protected_field_service.set_protected_field`
can be told to write `source="AI"` instead of the default `"APP"`. Every
existing (human-facing) call site is untouched — these are new optional
keyword-only parameters, not a signature break.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.models.user import UserRole
from app.schemas.record import UpdateRecordRequest
from app.services import record_service
from app.services.audit_service import write_audit_log
from app.services.protected_field_service import set_protected_field


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": "d1"}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


class TestWriteAuditLogAiSessionId:
    async def test_ai_session_id_is_persisted(
        self, session: AsyncSession, company: uuid.UUID, owner: uuid.UUID
    ) -> None:
        ai_session_id = uuid.uuid4()
        await session.execute(
            text("INSERT INTO ai_sessions (id, company_id, user_id) VALUES (:id, :cid, :uid)"),
            {"id": str(ai_session_id), "cid": str(company), "uid": str(owner)},
        )
        await write_audit_log(
            session,
            company_id=company,
            action="AI_PROPOSAL_CREATED",
            entity_type="ai_proposal",
            entity_id=uuid.uuid4(),
            actor_user_id=owner,
            actor_role="OWNER",
            source="AI",
            ai_session_id=ai_session_id,
        )
        await session.commit()

        row = (
            await session.execute(
                text("SELECT source, ai_session_id FROM audit_logs WHERE company_id = :cid"),
                {"cid": str(company)},
            )
        ).one()

        assert row.source == "AI"
        assert str(row.ai_session_id) == str(ai_session_id)

    async def test_omitted_ai_session_id_stays_null(
        self, session: AsyncSession, company: uuid.UUID, owner: uuid.UUID
    ) -> None:
        await write_audit_log(
            session,
            company_id=company,
            action="RECORD_UPDATE",
            entity_type="record",
            entity_id=uuid.uuid4(),
            actor_user_id=owner,
            actor_role="OWNER",
        )
        await session.commit()

        row = (
            await session.execute(
                text("SELECT source, ai_session_id FROM audit_logs WHERE company_id = :cid"),
                {"cid": str(company)},
            )
        ).one()

        assert row.source == "APP"
        assert row.ai_session_id is None


class TestUpdateRecordSourceOverride:
    async def test_default_source_is_app(
        self,
        client: AsyncClient,
        session: AsyncSession,
        company: uuid.UUID,
        owner: uuid.UUID,
        owner_password: str,
    ) -> None:
        headers = {
            "Authorization": f"Bearer {await _login(client, 'owner@test.lk', owner_password)}"
        }
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

        ctx = SecurityContext(user_id=owner, company_id=company, role=UserRole.OWNER, store_ids=())
        await record_service.update_record(
            session,
            ctx,
            uuid.UUID(record["id"]),
            UpdateRecordRequest(data={"text": "changed"}),
            record["version"],
        )
        await session.commit()

        row = (
            await session.execute(
                text(
                    "SELECT source, ai_session_id FROM audit_logs "
                    "WHERE entity_id = :eid AND action = 'RECORD_UPDATE'"
                ),
                {"eid": record["id"]},
            )
        ).one()
        assert row.source == "APP"
        assert row.ai_session_id is None

    async def test_source_ai_is_forwarded_to_the_audit_entry(
        self,
        client: AsyncClient,
        session: AsyncSession,
        company: uuid.UUID,
        owner: uuid.UUID,
        owner_password: str,
    ) -> None:
        headers = {
            "Authorization": f"Bearer {await _login(client, 'owner@test.lk', owner_password)}"
        }
        page_resp = await client.post(
            "/pages",
            json={"name": "Notes 2", "columns": [{"name": "Text", "data_type": "TEXT"}]},
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

        ai_session_id = uuid.uuid4()
        await session.execute(
            text("INSERT INTO ai_sessions (id, company_id, user_id) VALUES (:id, :cid, :uid)"),
            {"id": str(ai_session_id), "cid": str(company), "uid": str(owner)},
        )

        ctx = SecurityContext(user_id=owner, company_id=company, role=UserRole.OWNER, store_ids=())
        await record_service.update_record(
            session,
            ctx,
            uuid.UUID(record["id"]),
            UpdateRecordRequest(data={"text": "changed by ai"}),
            record["version"],
            source="AI",
            ai_session_id=ai_session_id,
        )
        await session.commit()

        row = (
            await session.execute(
                text(
                    "SELECT source, ai_session_id FROM audit_logs "
                    "WHERE entity_id = :eid AND action = 'RECORD_UPDATE'"
                ),
                {"eid": record["id"]},
            )
        ).one()
        assert row.source == "AI"
        assert str(row.ai_session_id) == str(ai_session_id)


class TestSetProtectedFieldSourceOverride:
    async def test_source_ai_is_forwarded_to_the_audit_entry(
        self,
        client: AsyncClient,
        session: AsyncSession,
        company: uuid.UUID,
        owner: uuid.UUID,
        owner_password: str,
        system_page_ids: dict[str, str],
    ) -> None:
        headers = {
            "Authorization": f"Bearer {await _login(client, 'owner@test.lk', owner_password)}"
        }
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
        record_id = uuid.UUID(record["id"])

        ai_session_id = uuid.uuid4()
        await session.execute(
            text("INSERT INTO ai_sessions (id, company_id, user_id) VALUES (:id, :cid, :uid)"),
            {"id": str(ai_session_id), "cid": str(company), "uid": str(owner)},
        )

        ctx = SecurityContext(user_id=owner, company_id=company, role=UserRole.OWNER, store_ids=())
        await set_protected_field(
            session,
            ctx,
            record_id,
            "cheque_status",
            "PAID",
            record["version"],
            source="AI",
            ai_session_id=ai_session_id,
        )
        await session.commit()

        row = (
            await session.execute(
                text(
                    "SELECT source, ai_session_id FROM audit_logs "
                    "WHERE entity_id = :eid AND action = 'PROTECTED_FIELD_CHANGE'"
                ),
                {"eid": str(record_id)},
            )
        ).one()
        assert row.source == "AI"
        assert str(row.ai_session_id) == str(ai_session_id)
