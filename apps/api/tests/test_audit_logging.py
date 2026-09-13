"""Every mutation writes exactly one audit entry with the right `page_id`
(plan section 18.2, P5) — the gap this phase closes: `write_audit_log` never
populated `page_id` before, even though the column and every relevant call
site's own `page`/`page_id` were already there.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Row
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


async def _create_page(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/pages",
        json={
            "name": "Audit Test Page",
            "columns": [{"name": "Amount", "data_type": "CURRENCY", "is_required": True}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _latest_audit_row(session: AsyncSession, company_id: uuid.UUID, action: str) -> Row:
    return (
        await session.execute(
            text(
                "SELECT page_id, old_data, new_data, entity_type FROM audit_logs "
                "WHERE company_id = :cid AND action = :action "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"cid": str(company_id), "action": action},
        )
    ).one()


class TestRecordAuditing:
    async def test_record_create_writes_audit_entry_with_page_id(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        company: uuid.UUID, session: AsyncSession,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        resp = await client.post(
            f"/pages/{page_id}/records",
            json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"amount": "100.00"}},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

        row = await _latest_audit_row(session, company, "RECORD_CREATE")
        assert str(row.page_id) == page_id
        assert row.new_data["amount"] == "100.00"

    async def test_record_update_writes_old_and_new_data_with_page_id(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        company: uuid.UUID, session: AsyncSession,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        create = await client.post(
            f"/pages/{page_id}/records",
            json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"amount": "100.00"}},
            headers=headers,
        )
        record = create.json()

        resp = await client.patch(
            f"/records/{record['id']}",
            json={"version": record["version"], "data": {"amount": "200.00"}},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

        row = await _latest_audit_row(session, company, "RECORD_UPDATE")
        assert str(row.page_id) == page_id
        assert row.old_data["amount"] == "100.00"
        assert row.new_data["amount"] == "200.00"


class TestSchemaAuditing:
    async def test_column_create_writes_audit_entry_with_page_id(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        company: uuid.UUID, session: AsyncSession,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        resp = await client.post(
            f"/pages/{page_id}/columns",
            json={"name": "Note", "data_type": "TEXT"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

        row = await _latest_audit_row(session, company, "COLUMN_CREATE")
        assert str(row.page_id) == page_id
        assert row.new_data["name"] == "Note"

    async def test_page_access_grant_writes_audit_entry_with_page_id(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, company: uuid.UUID, session: AsyncSession,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers)
        resp = await client.put(
            f"/pages/{page_id}/access",
            json={"grants": [{"user_id": str(manager), "can_view": True, "can_create": False}]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

        row = await _latest_audit_row(session, company, "PAGE_ACCESS_UPDATE")
        assert str(row.page_id) == page_id


class TestPermissionDeniedAuditing:
    async def test_owner_only_denial_has_null_page_id(
        self, client: AsyncClient, manager: uuid.UUID, manager_password: str,
        company: uuid.UUID, session: AsyncSession,
    ) -> None:
        headers = await _manager_headers(client, manager_password)
        resp = await client.get("/users", headers=headers)
        assert resp.status_code == 403

        row = await _latest_audit_row(session, company, "PERMISSION_DENIED")
        assert row.page_id is None

    async def test_page_access_denial_has_the_pages_own_page_id(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str, company: uuid.UUID, session: AsyncSession,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, owner_headers)

        manager_headers = await _manager_headers(client, manager_password)
        # The manager has no grant at all on this page -> 404, but the denial
        # is still audited with the page_id now available to `require_page_access`.
        resp = await client.get(f"/pages/{page_id}/records", headers=manager_headers)
        assert resp.status_code == 404

        row = await _latest_audit_row(session, company, "PERMISSION_DENIED")
        assert str(row.page_id) == page_id
