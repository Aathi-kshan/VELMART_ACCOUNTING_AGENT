"""`GET /audit-logs` / `GET /audit-logs/export` (plan section 18.3, P5) — the
Owner-facing read API: manager visibility filtering, the sentence
formatter, and cursor pagination.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import text
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


async def _create_page(client: AsyncClient, headers: dict[str, str], name: str) -> str:
    resp = await client.post(
        "/pages",
        json={
            "name": name,
            "columns": [{"name": "Amount", "data_type": "CURRENCY", "is_required": True}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


class TestVisibility:
    async def test_owner_sees_all_company_audit_logs(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        await _create_page(client, headers, "Owner Visible Page")

        resp = await client.get("/audit-logs", headers=headers)
        assert resp.status_code == 200, resp.text
        actions = {item["action"] for item in resp.json()["items"]}
        assert "PAGE_CREATE" in actions
        assert "LOGIN" in actions

    async def test_manager_sees_only_view_granted_pages(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        manager: uuid.UUID,
        manager_password: str,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        granted_page = await _create_page(client, owner_headers, "Granted Page")
        await _create_page(client, owner_headers, "Ungranted Page")
        grant = await client.put(
            f"/pages/{granted_page}/access",
            json={"grants": [{"user_id": str(manager), "can_view": True, "can_create": True}]},
            headers=owner_headers,
        )
        assert grant.status_code == 200, grant.text

        manager_headers = await _manager_headers(client, manager_password)
        resp = await client.get("/audit-logs", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        page_ids = {item["page_id"] for item in resp.json()["items"] if item["page_id"]}
        assert page_ids == {granted_page}

    async def test_manager_never_sees_null_page_id_entries(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        manager: uuid.UUID,
        manager_password: str,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, owner_headers, "Some Page")
        await client.put(
            f"/pages/{page_id}/access",
            json={"grants": [{"user_id": str(manager), "can_view": True, "can_create": True}]},
            headers=owner_headers,
        )

        manager_headers = await _manager_headers(client, manager_password)
        resp = await client.get("/audit-logs", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        # LOGIN/USER_CREATE-style entries (page_id IS NULL) never leak to a
        # manager, even though a LOGIN happened for both roles in this test.
        assert all(item["page_id"] is not None for item in resp.json()["items"])


class TestFiltersAndPagination:
    async def test_filter_by_actor_user_id(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        await _create_page(client, headers, "Filter Test Page")

        resp = await client.get(
            "/audit-logs", params={"actor_user_id": str(owner)}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        assert all(item["actor_name"] for item in resp.json()["items"])

    async def test_filter_by_page_id(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_a = await _create_page(client, headers, "Page A")
        await _create_page(client, headers, "Page B")

        resp = await client.get("/audit-logs", params={"page_id": page_a}, headers=headers)
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert items
        assert all(item["page_id"] == page_a for item in items)

    async def test_cursor_pagination_is_stable_and_covers_every_row_once(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        for i in range(5):
            await _create_page(client, headers, f"Pagination Page {i}")

        seen_ids: set[int] = set()
        cursor = None
        for _ in range(20):
            resp = await client.get(
                "/audit-logs",
                params={"limit": 2, **({"cursor": cursor} if cursor else {})},
                headers=headers,
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            for item in body["items"]:
                assert item["id"] not in seen_ids, "duplicate row across pages"
                seen_ids.add(item["id"])
            if not body["has_more"]:
                break
            cursor = body["next_cursor"]
        assert len(seen_ids) >= 5


class TestExport:
    async def test_export_is_owner_only(
        self, client: AsyncClient, manager: uuid.UUID, manager_password: str
    ) -> None:
        headers = await _manager_headers(client, manager_password)
        resp = await client.get("/audit-logs/export", headers=headers)
        assert resp.status_code == 403

    async def test_owner_can_export_csv(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        await _create_page(client, headers, "Export Test Page")

        resp = await client.get("/audit-logs/export", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/csv")
        body = resp.content.decode("utf-8-sig")
        assert "PAGE_CREATE" in body


class TestSentenceFormatter:
    async def test_record_update_sentence_names_the_changed_field(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, headers, "Sentence Test Page")
        create = await client.post(
            f"/pages/{page_id}/records",
            json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"amount": "100.00"}},
            headers=headers,
        )
        record = create.json()
        await client.patch(
            f"/records/{record['id']}",
            json={"version": record["version"], "data": {"amount": "200.00"}},
            headers=headers,
        )

        resp = await client.get(
            "/audit-logs", params={"page_id": page_id, "entity_type": "record"}, headers=headers
        )
        sentences = [item["sentence"] for item in resp.json()["items"]]
        assert any("amount" in s and "100.00" in s and "200.00" in s for s in sentences)

    async def test_unmatched_action_falls_back_to_a_generic_sentence(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        company: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        await session.execute(
            text(
                "INSERT INTO audit_logs (company_id, actor_user_id, actor_role, action, "
                "entity_type, source, row_hash) VALUES "
                "(:cid, :uid, 'OWNER', 'SOME_FUTURE_ACTION', 'widget', 'APP', '')"
            ),
            {"cid": str(company), "uid": str(owner)},
        )
        await session.commit()

        headers = await _owner_headers(client, owner_password)
        resp = await client.get(
            "/audit-logs", params={"entity_type": "widget"}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert items
        assert "some future action" in items[0]["sentence"].lower()

    async def test_ai_source_appends_via_ai_suffix(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        company: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        await session.execute(
            text(
                "INSERT INTO audit_logs (company_id, actor_user_id, actor_role, action, "
                "entity_type, source, row_hash) VALUES "
                "(:cid, :uid, 'OWNER', 'RECORD_UPDATE', 'record', 'AI', '')"
            ),
            {"cid": str(company), "uid": str(owner)},
        )
        await session.commit()

        headers = await _owner_headers(client, owner_password)
        resp = await client.get(
            "/audit-logs", params={"entity_type": "record"}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        sentences = [item["sentence"] for item in resp.json()["items"]]
        assert any(s.endswith("via AI") for s in sentences)
