"""The Owner's side of protected-field enforcement (plan section 11.4,
docs/API.md §1.4): `PATCH /records/{id}/protected-field` is the only way
`cheques.cheque_status` ever changes after create, and every change is
audited as `PROTECTED_FIELD_CHANGE` with the old and new value.

`TestGenericPageProtectedColumn` is P4's addition (plan §7/§11): every test
above exercises the `cheques` system page specifically — this class proves
the mechanism is generic, not special-cased to one hard-coded page, against
an ordinary Owner-created page with an Owner-defined protected column.
"""

from __future__ import annotations

import uuid
from typing import Any

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


async def _create_cheque(
    client: AsyncClient, headers: dict[str, str], page_id: str
) -> dict[str, Any]:
    resp = await client.post(
        f"/pages/{page_id}/records",
        json={
            "occurred_at": "2026-09-01T10:00:00+05:30",
            "data": {"cheque_number": "CHQ-100", "amount": "20000.00"},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_owner_can_change_cheque_status(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)
    record = await _create_cheque(client, headers, system_page_ids["cheques"])
    assert record["data"]["cheque_status"] == "PENDING"

    resp = await client.patch(
        f"/records/{record['id']}/protected-field",
        json={"column_key": "cheque_status", "value": "PAID", "version": record["version"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["cheque_status"] == "PAID"
    assert body["version"] == record["version"] + 1


async def test_stale_version_is_conflict(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)
    record = await _create_cheque(client, headers, system_page_ids["cheques"])

    resp = await client.patch(
        f"/records/{record['id']}/protected-field",
        json={"column_key": "cheque_status", "value": "PAID", "version": record["version"] + 1},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "VERSION_CONFLICT"


async def test_invalid_option_is_422(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)
    record = await _create_cheque(client, headers, system_page_ids["cheques"])

    resp = await client.patch(
        f"/records/{record['id']}/protected-field",
        json={"column_key": "cheque_status", "value": "CANCELLED", "version": record["version"]},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text


class TestGenericPageProtectedColumn:
    async def _create_page(self, client: AsyncClient, headers: dict[str, str]) -> str:
        resp = await client.post(
            "/pages",
            json={
                "name": "Approvals",
                "columns": [
                    {"name": "Amount", "data_type": "CURRENCY", "is_required": True},
                    {
                        "name": "Status",
                        "data_type": "SELECT",
                        "is_protected": True,
                        "config": {"options": ["PENDING", "APPROVED"], "default": "PENDING"},
                    },
                ],
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        return str(resp.json()["id"])

    async def _create_record(
        self, client: AsyncClient, headers: dict[str, str], page_id: str
    ) -> dict[str, Any]:
        resp = await client.post(
            f"/pages/{page_id}/records",
            json={
                "occurred_at": "2026-09-07T10:00:00+05:30",
                "data": {"amount": "500.00"},
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    async def test_owner_can_change_a_generic_pages_protected_column(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await self._create_page(client, headers)
        record = await self._create_record(client, headers, page_id)
        assert record["data"]["status"] == "PENDING"

        resp = await client.patch(
            f"/records/{record['id']}/protected-field",
            json={"column_key": "status", "value": "APPROVED", "version": record["version"]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "APPROVED"

    async def test_generic_update_still_rejects_touching_it(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await self._create_page(client, headers)
        record = await self._create_record(client, headers, page_id)

        resp = await client.patch(
            f"/records/{record['id']}",
            json={"version": record["version"], "data": {"status": "APPROVED"}},
            headers=headers,
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["code"] == "PROTECTED_FIELD_FORBIDDEN"
