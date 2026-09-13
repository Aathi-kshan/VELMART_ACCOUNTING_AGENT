"""RESERVED_PAGE_KEY (plan sections 3.5.3, 10.3; docs/API.md §1.7) — an
Owner cannot create a page whose derived key collides with one of the six
system pages, including near-miss singular/plural variants, so a
same-sounding page can never become a second, competing source of truth for
the same data. `page_service.create_page` already checks this (P3); this
file is the dedicated test the P3.5 plan asks for.
"""

from __future__ import annotations

import uuid

import pytest
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


@pytest.mark.parametrize(
    "name",
    ["Cheque", "Cheques", "Salary", "Salaries", "Expense", "Expenses", "Purchase", "Purchases"],
)
async def test_reserved_and_near_miss_names_are_rejected(
    client: AsyncClient, owner: uuid.UUID, owner_password: str, name: str
) -> None:
    headers = await _owner_headers(client, owner_password)
    resp = await client.post("/pages", json={"name": name, "columns": []}, headers=headers)
    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "RESERVED_PAGE_KEY"


async def test_a_genuinely_new_name_is_accepted(
    client: AsyncClient, owner: uuid.UUID, owner_password: str
) -> None:
    headers = await _owner_headers(client, owner_password)
    resp = await client.post(
        "/pages", json={"name": "Supplier Invoices", "columns": []}, headers=headers
    )
    assert resp.status_code == 201, resp.text
