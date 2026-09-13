"""The manager side of protected-field enforcement (plan section 11.4,
docs/API.md §1.4): a manager cannot supply a protected column's value at
create — not even the correct default — and cannot reach the dedicated
protected-field endpoint at all. Nobody, owner included, changes a
protected column through the generic `PATCH /records/{id}`.
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


async def _grant(
    client: AsyncClient, owner_headers: dict[str, str], page_id: str, user_id: uuid.UUID
) -> None:
    resp = await client.put(
        f"/pages/{page_id}/access",
        json={"grants": [{"user_id": str(user_id), "can_view": True, "can_create": True}]},
        headers=owner_headers,
    )
    assert resp.status_code == 200, resp.text


async def test_manager_create_without_cheque_status_gets_the_default(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
    system_page_ids: dict[str, str],
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    page_id = system_page_ids["cheques"]
    await _grant(client, owner_headers, page_id, manager)

    manager_headers = await _manager_headers(client, manager_password)
    resp = await client.post(
        f"/pages/{page_id}/records",
        json={
            "occurred_at": "2026-09-02T10:00:00+05:30",
            "data": {"cheque_number": "CHQ-200", "amount": "5000.00"},
        },
        headers=manager_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["cheque_status"] == "PENDING"


async def test_manager_create_supplying_cheque_status_is_403(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
    system_page_ids: dict[str, str],
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    page_id = system_page_ids["cheques"]
    await _grant(client, owner_headers, page_id, manager)

    manager_headers = await _manager_headers(client, manager_password)
    resp = await client.post(
        f"/pages/{page_id}/records",
        json={
            "occurred_at": "2026-09-02T10:00:00+05:30",
            "data": {"cheque_number": "CHQ-201", "amount": "5000.00", "cheque_status": "PENDING"},
        },
        headers=manager_headers,
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "PROTECTED_FIELD_FORBIDDEN"


async def test_manager_cannot_reach_the_protected_field_endpoint(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    manager: uuid.UUID,
    manager_password: str,
    system_page_ids: dict[str, str],
) -> None:
    owner_headers = await _owner_headers(client, owner_password)
    page_id = system_page_ids["cheques"]
    await _grant(client, owner_headers, page_id, manager)

    created = await client.post(
        f"/pages/{page_id}/records",
        json={
            "occurred_at": "2026-09-02T10:00:00+05:30",
            "data": {"cheque_number": "CHQ-202", "amount": "5000.00"},
        },
        headers=owner_headers,
    )
    assert created.status_code == 201, created.text
    record = created.json()

    manager_headers = await _manager_headers(client, manager_password)
    resp = await client.patch(
        f"/records/{record['id']}/protected-field",
        json={"column_key": "cheque_status", "value": "PAID", "version": record["version"]},
        headers=manager_headers,
    )
    assert resp.status_code == 403, resp.text


async def test_owner_cannot_change_cheque_status_via_generic_patch(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    headers = await _owner_headers(client, owner_password)
    page_id = system_page_ids["cheques"]
    created = await client.post(
        f"/pages/{page_id}/records",
        json={
            "occurred_at": "2026-09-02T10:00:00+05:30",
            "data": {"cheque_number": "CHQ-203", "amount": "5000.00"},
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    record = created.json()

    resp = await client.patch(
        f"/records/{record['id']}",
        json={"version": record["version"], "data": {"cheque_status": "PAID"}},
        headers=headers,
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "PROTECTED_FIELD_FORBIDDEN"


async def test_editing_an_unrelated_field_does_not_403(
    client: AsyncClient,
    owner: uuid.UUID,
    owner_password: str,
    system_page_ids: dict[str, str],
) -> None:
    """P4 bug fix (found while planning P4): a client that round-trips a
    record's full data on every edit — as `record_form_screen.dart` does —
    always resubmits a protected column's *current, unchanged* value
    alongside whatever it actually meant to change. That must not 403;
    only a genuine attempted change to the protected value should."""
    headers = await _owner_headers(client, owner_password)
    page_id = system_page_ids["cheques"]
    created = await client.post(
        f"/pages/{page_id}/records",
        json={
            "occurred_at": "2026-09-02T10:00:00+05:30",
            "data": {"cheque_number": "CHQ-204", "amount": "5000.00"},
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["data"]["cheque_status"] == "PENDING"

    # Resubmits the whole record's current data, unchanged, except amount —
    # exactly what record_form_screen.dart's edit mode does.
    resp = await client.patch(
        f"/records/{record['id']}",
        json={
            "version": record["version"],
            "data": {**record["data"], "amount": "6000.00"},
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["amount"] == "6000.00"
    assert body["data"]["cheque_status"] == "PENDING"
