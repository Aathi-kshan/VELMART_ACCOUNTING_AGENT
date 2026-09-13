"""Page access grants — the 🟡 filtered case `test_permissions_matrix.py`
deliberately excludes (plan sections 3.10, 4.3; docs/API.md §1.4).

Default-deny: a page with no grant row is invisible to a manager everywhere
(list, schema, records, query, aggregate, column-values) — 404, never 403,
so a denial can't be used to confirm the page exists. A grant that exists
but lacks the specific permission asked for (view vs. create) is a 403,
since the page is already known to be real to that caller.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient


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
        json={"name": "Access Page", "columns": [{"name": "Note", "data_type": "TEXT"}]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _grant(
    client: AsyncClient,
    owner_headers: dict[str, str],
    page_id: str,
    user_id: uuid.UUID,
    *,
    can_view: bool = True,
    can_create: bool = True,
) -> None:
    resp = await client.put(
        f"/pages/{page_id}/access",
        json={
            "grants": [
                {"user_id": str(user_id), "can_view": can_view, "can_create": can_create}
            ]
        },
        headers=owner_headers,
    )
    assert resp.status_code == 200, resp.text


class TestNoGrant:
    async def test_manager_without_grant_gets_404_on_schema(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, owner_headers)

        manager_headers = await _manager_headers(client, manager_password)
        resp = await client.get(f"/pages/{page_id}/schema", headers=manager_headers)
        assert resp.status_code == 404

    async def test_manager_without_grant_gets_404_on_records(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, owner_headers)

        manager_headers = await _manager_headers(client, manager_password)
        resp = await client.get(f"/pages/{page_id}/records", headers=manager_headers)
        assert resp.status_code == 404

    async def test_manager_without_grant_gets_404_on_create(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, owner_headers)

        manager_headers = await _manager_headers(client, manager_password)
        resp = await client.post(
            f"/pages/{page_id}/records",
            json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"note": "x"}},
            headers=manager_headers,
        )
        assert resp.status_code == 404

    async def test_manager_without_grant_gets_404_on_query_and_aggregate(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, owner_headers)
        manager_headers = await _manager_headers(client, manager_password)

        query = await client.post(
            f"/pages/{page_id}/records/query", json={}, headers=manager_headers
        )
        assert query.status_code == 404

        aggregate = await client.post(
            f"/pages/{page_id}/aggregate", json={"metric": "count"}, headers=manager_headers
        )
        assert aggregate.status_code == 404

    async def test_page_without_any_grant_is_absent_from_managers_list(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        await _create_page(client, owner_headers)

        manager_headers = await _manager_headers(client, manager_password)
        resp = await client.get("/pages", headers=manager_headers)
        assert resp.status_code == 200
        assert resp.json() == []


class TestViewOnlyGrant:
    async def test_manager_with_view_only_can_read_but_not_create(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, owner_headers)
        await _grant(client, owner_headers, page_id, manager, can_view=True, can_create=False)

        manager_headers = await _manager_headers(client, manager_password)
        schema = await client.get(f"/pages/{page_id}/schema", headers=manager_headers)
        assert schema.status_code == 200

        create = await client.post(
            f"/pages/{page_id}/records",
            json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"note": "x"}},
            headers=manager_headers,
        )
        assert create.status_code == 403

    async def test_page_with_view_grant_appears_in_managers_list(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, owner_headers)
        await _grant(client, owner_headers, page_id, manager, can_view=True, can_create=False)

        manager_headers = await _manager_headers(client, manager_password)
        resp = await client.get("/pages", headers=manager_headers)
        assert resp.status_code == 200
        assert [p["id"] for p in resp.json()] == [page_id]


class TestViewAndCreateGrant:
    async def test_manager_with_full_grant_can_create_and_read(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, owner_headers)
        await _grant(client, owner_headers, page_id, manager, can_view=True, can_create=True)

        manager_headers = await _manager_headers(client, manager_password)
        create = await client.post(
            f"/pages/{page_id}/records",
            json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"note": "hello"}},
            headers=manager_headers,
        )
        assert create.status_code == 201, create.text

        listing = await client.get(f"/pages/{page_id}/records", headers=manager_headers)
        assert listing.status_code == 200
        assert len(listing.json()["items"]) == 1


class TestOwnerBypassesGrants:
    async def test_owner_never_needs_a_grant(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, owner_headers)
        resp = await client.get(f"/pages/{page_id}/schema", headers=owner_headers)
        assert resp.status_code == 200


class TestPutAccessReplacesWholesale:
    async def test_put_access_replaces_grants_entirely(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, owner_headers)
        await _grant(client, owner_headers, page_id, manager, can_view=True, can_create=True)

        manager_headers = await _manager_headers(client, manager_password)
        before = await client.get(f"/pages/{page_id}/schema", headers=manager_headers)
        assert before.status_code == 200

        # Replacing with an empty grant list revokes access entirely.
        resp = await client.put(
            f"/pages/{page_id}/access", json={"grants": []}, headers=owner_headers
        )
        assert resp.status_code == 200

        after = await client.get(f"/pages/{page_id}/schema", headers=manager_headers)
        assert after.status_code == 404

    async def test_put_access_is_owner_only(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        manager: uuid.UUID, manager_password: str,
    ) -> None:
        owner_headers = await _owner_headers(client, owner_password)
        page_id = await _create_page(client, owner_headers)

        manager_headers = await _manager_headers(client, manager_password)
        resp = await client.put(
            f"/pages/{page_id}/access", json={"grants": []}, headers=manager_headers
        )
        assert resp.status_code == 403
