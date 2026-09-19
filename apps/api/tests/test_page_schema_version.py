"""`pages.version` must actually track the page's schema.

The column exists (migration 0002), is `NOT NULL DEFAULT 1`, and is exposed
on every `PageOut`/`PageSchemaOut` — but **nothing ever incremented it**. It
sat at 1 for the life of a page no matter how many times the page was renamed
or its columns added, retyped, or archived.

Two consequences. A client holding a cached `PageSchema` had no way to tell
it had gone stale — which matters because the whole point of this engine is
that an Owner changes a page's columns and every client picks the change up
without an app release. And `version` being present in the response implies
optimistic locking that did not exist: any `If-Match: 1` was accepted
forever, so two Owners editing a page's structure at once silently
overwrote each other.

`If-Match` is honoured but not required here, deliberately: the Flutter
client sends it for records only (`page_repository.dart`), so demanding it on
schema edits would break every existing caller. Sending it opts into the
check; omitting it behaves as before.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _owner_headers(client: AsyncClient, owner_password: str) -> dict[str, str]:
    resp = await client.post(
        "/auth/login",
        json={"email": "owner@test.lk", "password": owner_password, "device_id": "d1"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _page(client: AsyncClient, headers: dict[str, str]) -> dict:
    resp = await client.post(
        "/pages",
        json={
            "name": f"Schema {uuid.uuid4().hex[:6]}",
            "columns": [{"name": "Note", "data_type": "TEXT"}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


async def _version(client: AsyncClient, headers: dict[str, str], page_id: str) -> int:
    resp = await client.get(f"/pages/{page_id}/schema", headers=headers)
    assert resp.status_code == 200, resp.text
    return int(resp.json()["version"])


class TestVersionMovesWhenTheSchemaChanges:
    async def test_a_new_page_starts_at_one(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _page(client, headers)
        assert page["version"] == 1

    async def test_renaming_the_page_bumps_it(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _page(client, headers)

        resp = await client.patch(
            f"/pages/{page['id']}", json={"name": "Renamed"}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        assert await _version(client, headers, page["id"]) == 2

    async def test_adding_a_column_bumps_it(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """A column change is a schema change — this is the case a cached
        client most needs to notice."""
        headers = await _owner_headers(client, owner_password)
        page = await _page(client, headers)

        resp = await client.post(
            f"/pages/{page['id']}/columns",
            json={"name": "Amount", "data_type": "CURRENCY"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        assert await _version(client, headers, page["id"]) == 2

    async def test_editing_a_column_bumps_it(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _page(client, headers)
        column_id = page["columns"][0]["id"]

        resp = await client.patch(
            f"/columns/{column_id}", json={"name": "Renamed Note"}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        assert await _version(client, headers, page["id"]) == 2

    async def test_archiving_a_column_bumps_it(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _page(client, headers)
        extra = await client.post(
            f"/pages/{page['id']}/columns",
            json={"name": "Spare", "data_type": "TEXT"},
            headers=headers,
        )
        assert extra.status_code == 201, extra.text

        resp = await client.delete(f"/columns/{extra.json()['id']}", headers=headers)
        assert resp.status_code == 200, resp.text
        assert await _version(client, headers, page["id"]) == 3

    async def test_successive_changes_keep_incrementing(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _page(client, headers)

        for expected in (2, 3, 4):
            resp = await client.patch(
                f"/pages/{page['id']}", json={"name": f"Rename {expected}"}, headers=headers
            )
            assert resp.status_code == 200, resp.text
            assert await _version(client, headers, page["id"]) == expected

    async def test_creating_a_record_does_not_bump_it(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """It is the *schema* version, not a row counter."""
        headers = await _owner_headers(client, owner_password)
        page = await _page(client, headers)

        created = await client.post(
            f"/pages/{page['id']}/records",
            json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"note": "x"}},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        assert await _version(client, headers, page["id"]) == 1


class TestIfMatchOnSchemaEdits:
    async def test_a_stale_version_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _page(client, headers)

        first = await client.patch(
            f"/pages/{page['id']}",
            json={"name": "First"},
            headers={**headers, "If-Match": "1"},
        )
        assert first.status_code == 200, first.text

        # Version 1 is now stale — this used to be accepted forever.
        stale = await client.patch(
            f"/pages/{page['id']}",
            json={"name": "Second"},
            headers={**headers, "If-Match": "1"},
        )
        assert stale.status_code == 409, stale.text
        assert stale.json()["code"] == "VERSION_CONFLICT"

        # The rejected edit must not have landed.
        schema = await client.get(f"/pages/{page['id']}/schema", headers=headers)
        assert schema.json()["name"] == "First"

    async def test_the_current_version_is_accepted(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _page(client, headers)

        first = await client.patch(
            f"/pages/{page['id']}",
            json={"name": "First"},
            headers={**headers, "If-Match": "1"},
        )
        assert first.status_code == 200, first.text

        second = await client.patch(
            f"/pages/{page['id']}",
            json={"name": "Second"},
            headers={**headers, "If-Match": "2"},
        )
        assert second.status_code == 200, second.text

    async def test_omitting_it_still_works(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """The existing Flutter client does not send `If-Match` on schema
        edits, so requiring it would break every current caller."""
        headers = await _owner_headers(client, owner_password)
        page = await _page(client, headers)

        resp = await client.patch(
            f"/pages/{page['id']}", json={"name": "No header"}, headers=headers
        )
        assert resp.status_code == 200, resp.text

    async def test_a_non_integer_if_match_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page = await _page(client, headers)

        resp = await client.patch(
            f"/pages/{page['id']}",
            json={"name": "Bad"},
            headers={**headers, "If-Match": "not-a-number"},
        )
        assert resp.status_code == 422, resp.text
