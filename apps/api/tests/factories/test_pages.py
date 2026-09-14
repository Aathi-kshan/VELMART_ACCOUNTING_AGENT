"""Slice 13 self-check — each fixture factory produces the expected page/
column/record shape, and Fixture A and Fixture B never collide.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.factories.pages import FIXTURE_A_PAGE, FIXTURE_B_PAGE, build_fixture_a, build_fixture_b


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": "d1"}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


class TestFixtureADistinctFromFixtureB:
    def test_names_and_column_shapes_differ(self) -> None:
        assert FIXTURE_A_PAGE["name"] != FIXTURE_B_PAGE["name"]
        a_columns = [c["name"] for c in FIXTURE_A_PAGE["columns"]]
        b_columns = [c["name"] for c in FIXTURE_B_PAGE["columns"]]
        assert a_columns != b_columns


class TestBuildFixtureA:
    async def test_produces_the_expected_page_columns_and_records(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        system_page_ids: dict[str, str],
    ) -> None:
        headers = {
            "Authorization": f"Bearer {await _login(client, 'owner@test.lk', owner_password)}"
        }

        page = await build_fixture_a(client, headers, system_page_ids)

        assert page["key"] == "vehicle_costs"
        assert {c["key"] for c in page["columns"]} == {"vehicle", "litres", "cost", "category"}

        list_resp = await client.get(f"/pages/{page['id']}/records", headers=headers)
        assert list_resp.status_code == 200, list_resp.text
        assert len(list_resp.json()["items"]) == len(FIXTURE_A_PAGE["rows"])

    async def test_seeds_the_six_system_pages_too(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        system_page_ids: dict[str, str],
    ) -> None:
        headers = {
            "Authorization": f"Bearer {await _login(client, 'owner@test.lk', owner_password)}"
        }

        await build_fixture_a(client, headers, system_page_ids)

        expenses_resp = await client.get(
            f"/pages/{system_page_ids['expenses']}/records", headers=headers
        )
        assert expenses_resp.status_code == 200, expenses_resp.text
        assert len(expenses_resp.json()["items"]) == 3


class TestBuildFixtureB:
    async def test_produces_a_structurally_different_page(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        system_page_ids: dict[str, str],
    ) -> None:
        headers = {
            "Authorization": f"Bearer {await _login(client, 'owner@test.lk', owner_password)}"
        }

        page = await build_fixture_b(client, headers, system_page_ids)

        assert page["key"] == "operational_outlay"
        assert {c["key"] for c in page["columns"]} == {"department", "item", "qty", "amount"}

        list_resp = await client.get(f"/pages/{page['id']}/records", headers=headers)
        assert list_resp.status_code == 200, list_resp.text
        assert len(list_resp.json()["items"]) == len(FIXTURE_B_PAGE["rows"])
