"""Optimistic locking on record updates (plan section 21.1; docs/API.md
§1.2). Every mutable row carries a `version`; `PATCH /records/{id}` accepts
either an `If-Match` header or a body `version` field, and a mismatch is a
409 that surfaces the row's current version so the caller can refetch and
retry.
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


async def _create_page_and_record(
    client: AsyncClient, headers: dict[str, str]
) -> tuple[str, dict]:
    page = await client.post(
        "/pages",
        json={"name": "Locking Page", "columns": [{"name": "Note", "data_type": "TEXT"}]},
        headers=headers,
    )
    assert page.status_code == 201, page.text
    page_id = page.json()["id"]

    record = await client.post(
        f"/pages/{page_id}/records",
        json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"note": "first"}},
        headers=headers,
    )
    assert record.status_code == 201, record.text
    return page_id, record.json()


class TestVersionRequired:
    async def test_update_without_any_version_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        _, record = await _create_page_and_record(client, headers)

        resp = await client.patch(
            f"/records/{record['id']}", json={"data": {"note": "second"}}, headers=headers
        )
        assert resp.status_code == 422


class TestIfMatchHeader:
    async def test_correct_if_match_succeeds_and_bumps_version(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        _, record = await _create_page_and_record(client, headers)
        assert record["version"] == 1

        resp = await client.patch(
            f"/records/{record['id']}",
            json={"data": {"note": "second"}},
            headers={**headers, "If-Match": "1"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["version"] == 2
        assert resp.json()["data"]["note"] == "second"

    async def test_stale_if_match_is_409_with_current_version(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        _, record = await _create_page_and_record(client, headers)

        first = await client.patch(
            f"/records/{record['id']}",
            json={"data": {"note": "second"}},
            headers={**headers, "If-Match": "1"},
        )
        assert first.status_code == 200

        # Replaying the now-stale version-1 If-Match.
        stale = await client.patch(
            f"/records/{record['id']}",
            json={"data": {"note": "third"}},
            headers={**headers, "If-Match": "1"},
        )
        assert stale.status_code == 409
        body = stale.json()
        assert body["code"] == "VERSION_CONFLICT"
        assert body["current_version"] == 2

    async def test_non_integer_if_match_is_rejected(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        _, record = await _create_page_and_record(client, headers)

        resp = await client.patch(
            f"/records/{record['id']}",
            json={"data": {"note": "second"}},
            headers={**headers, "If-Match": "not-a-number"},
        )
        assert resp.status_code == 422


class TestBodyVersionField:
    async def test_correct_body_version_succeeds(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        _, record = await _create_page_and_record(client, headers)

        resp = await client.patch(
            f"/records/{record['id']}",
            json={"version": 1, "data": {"note": "second"}},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 2

    async def test_stale_body_version_is_409(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        _, record = await _create_page_and_record(client, headers)

        resp = await client.patch(
            f"/records/{record['id']}",
            json={"version": 99, "data": {"note": "second"}},
            headers=headers,
        )
        assert resp.status_code == 409
        assert resp.json()["current_version"] == 1

    async def test_if_match_header_wins_over_body_version_when_both_given(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        _, record = await _create_page_and_record(client, headers)

        # Correct header, deliberately wrong body version — header wins.
        resp = await client.patch(
            f"/records/{record['id']}",
            json={"version": 99, "data": {"note": "second"}},
            headers={**headers, "If-Match": "1"},
        )
        assert resp.status_code == 200, resp.text
