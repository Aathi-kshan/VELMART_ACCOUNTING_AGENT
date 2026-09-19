"""`store_id` and `store_ids` arrive in request bodies, and nothing checked them.

Two paths let a client name a store the server never verified:

* `POST/PATCH /records` accept a bare `store_id`. The RLS `store_scope`
  policy short-circuits for an OWNER (migration 0006), and `tenant_isolation`
  constrains only `company_id`, so an Owner could persist a record pointing
  at *another company's* store. A STORE_REF **column** was always checked
  (`record_service.validate_references`); the loose body field was not.
* `POST/PATCH /users` accept `store_ids`, written straight into
  `user_stores` — a table with no `company_id` column that is deliberately
  excluded from RLS. Those ids then become a manager's RLS store scope via
  `auth_service.store_ids_for`.

`tests/test_tenancy_isolation.py` covers reading across companies. This file
covers writing a foreign id *into* a row, which is the direction that leaves
bad data behind rather than simply returning nothing.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _owner_headers(client: AsyncClient, owner_password: str) -> dict[str, str]:
    resp = await client.post(
        "/auth/login",
        json={"email": "owner@test.lk", "password": owner_password, "device_id": "d1"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _foreign_store(session: AsyncSession) -> uuid.UUID:
    """A store belonging to an entirely different company."""
    company_id, store_id = uuid.uuid4(), uuid.uuid4()
    await session.execute(
        text("INSERT INTO companies (id, name) VALUES (:id, 'Rival Traders')"),
        {"id": str(company_id)},
    )
    await session.execute(
        text(
            "INSERT INTO stores (id, company_id, code, name) "
            "VALUES (:id, :company_id, 'RIVAL', 'Rival Main')"
        ),
        {"id": str(store_id), "company_id": str(company_id)},
    )
    await session.commit()
    return store_id


async def _own_store(session: AsyncSession, company: uuid.UUID) -> uuid.UUID:
    store_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO stores (id, company_id, code, name) "
            "VALUES (:id, :company_id, 'MAIN', 'Our Main')"
        ),
        {"id": str(store_id), "company_id": str(company)},
    )
    await session.commit()
    return store_id


async def _page(client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await client.post(
        "/pages",
        json={
            "name": f"Entries {uuid.uuid4().hex[:6]}",
            "columns": [{"name": "Note", "data_type": "TEXT"}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


class TestRecordStoreId:
    async def test_creating_a_record_for_another_companys_store_is_rejected(
        self,
        client: AsyncClient,
        session: AsyncSession,
        owner: uuid.UUID,
        owner_password: str,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _page(client, headers)
        foreign = await _foreign_store(session)

        resp = await client.post(
            f"/pages/{page_id}/records",
            json={
                "occurred_at": "2026-09-07T10:00:00+05:30",
                "store_id": str(foreign),
                "data": {"note": "planted"},
            },
            headers=headers,
        )
        assert resp.status_code in (403, 422), resp.text

        # Nothing may have been written carrying that store.
        count = await session.execute(
            text("SELECT count(*) FROM records WHERE store_id = :store_id"),
            {"store_id": str(foreign)},
        )
        assert count.scalar_one() == 0, "a record was persisted against a foreign store"

    async def test_updating_a_record_onto_another_companys_store_is_rejected(
        self,
        client: AsyncClient,
        session: AsyncSession,
        owner: uuid.UUID,
        owner_password: str,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _page(client, headers)
        created = await client.post(
            f"/pages/{page_id}/records",
            json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"note": "clean"}},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        record = created.json()
        foreign = await _foreign_store(session)

        resp = await client.patch(
            f"/records/{record['id']}",
            json={"store_id": str(foreign), "data": {"note": "moved"}},
            headers={**headers, "If-Match": str(record["version"])},
        )
        assert resp.status_code in (403, 422), resp.text

        row = await session.execute(
            text("SELECT store_id FROM records WHERE id = :id"), {"id": record["id"]}
        )
        assert row.scalar_one() is None, "an update moved a record to a foreign store"

    async def test_an_unknown_store_id_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _page(client, headers)

        resp = await client.post(
            f"/pages/{page_id}/records",
            json={
                "occurred_at": "2026-09-07T10:00:00+05:30",
                "store_id": str(uuid.uuid4()),
                "data": {"note": "nowhere"},
            },
            headers=headers,
        )
        assert resp.status_code in (403, 422), resp.text

    async def test_the_companys_own_store_is_still_accepted(
        self,
        client: AsyncClient,
        session: AsyncSession,
        company: uuid.UUID,
        owner: uuid.UUID,
        owner_password: str,
    ) -> None:
        """The guard must not break the ordinary case."""
        headers = await _owner_headers(client, owner_password)
        page_id = await _page(client, headers)
        mine = await _own_store(session, company)

        resp = await client.post(
            f"/pages/{page_id}/records",
            json={
                "occurred_at": "2026-09-07T10:00:00+05:30",
                "store_id": str(mine),
                "data": {"note": "fine"},
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["store_id"] == str(mine)


class TestUserStoreAssignments:
    async def test_assigning_a_manager_to_another_companys_store_is_rejected(
        self,
        client: AsyncClient,
        session: AsyncSession,
        owner: uuid.UUID,
        owner_password: str,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        foreign = await _foreign_store(session)

        resp = await client.post(
            "/users",
            json={
                "email": "newmanager@test.lk",
                "full_name": "New Manager",
                "password": "correct-horse-battery",
                "role": "MANAGER",
                "store_ids": [str(foreign)],
            },
            headers=headers,
        )
        assert resp.status_code in (403, 422), resp.text

        count = await session.execute(
            text("SELECT count(*) FROM user_stores WHERE store_id = :store_id"),
            {"store_id": str(foreign)},
        )
        assert count.scalar_one() == 0, "a manager was assigned to a foreign store"

    async def test_updating_a_manager_onto_another_companys_store_is_rejected(
        self,
        client: AsyncClient,
        session: AsyncSession,
        owner: uuid.UUID,
        manager: uuid.UUID,
        owner_password: str,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        foreign = await _foreign_store(session)

        resp = await client.patch(
            f"/users/{manager}",
            json={"store_ids": [str(foreign)]},
            headers=headers,
        )
        assert resp.status_code in (403, 422), resp.text

        count = await session.execute(
            text("SELECT count(*) FROM user_stores WHERE store_id = :store_id"),
            {"store_id": str(foreign)},
        )
        assert count.scalar_one() == 0

    async def test_assigning_a_manager_to_our_own_store_still_works(
        self,
        client: AsyncClient,
        session: AsyncSession,
        company: uuid.UUID,
        owner: uuid.UUID,
        manager: uuid.UUID,
        owner_password: str,
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        mine = await _own_store(session, company)

        resp = await client.patch(
            f"/users/{manager}", json={"store_ids": [str(mine)]}, headers=headers
        )
        assert resp.status_code == 200, resp.text

        count = await session.execute(
            text("SELECT count(*) FROM user_stores WHERE user_id = :u AND store_id = :s"),
            {"u": str(manager), "s": str(mine)},
        )
        assert count.scalar_one() == 1
