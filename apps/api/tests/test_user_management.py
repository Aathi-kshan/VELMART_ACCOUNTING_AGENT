"""PATCH /users/{id} role changes and deactivation (plan sections 4.2, 20.2,
21.2). Both must bump `token_version`, reusing the exact mechanism P1's
`test_token_version` already proved: any outstanding access token for that
user immediately stops working on `/me`, no matter how many devices it was
issued to.
"""

from __future__ import annotations

import asyncio
import uuid

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _login(client: AsyncClient, email: str, password: str) -> dict:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": "d1"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestRoleChangeBumpsTokenVersion:
    async def test_managers_old_token_stops_working_after_promotion(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str, manager: uuid.UUID,
        manager_password: str,
    ) -> None:
        owner_pair = await _login(client, "owner@test.lk", owner_password)
        manager_pair = await _login(client, "manager@test.lk", manager_password)

        # The manager's token works before the change.
        resp = await client.get(
            "/me", headers={"Authorization": f"Bearer {manager_pair['access_token']}"}
        )
        assert resp.status_code == 200

        patch = await client.patch(
            f"/users/{manager}",
            json={"role": "OWNER"},
            headers={"Authorization": f"Bearer {owner_pair['access_token']}"},
        )
        assert patch.status_code == 200
        assert patch.json()["role"] == "OWNER"

        resp = await client.get(
            "/me", headers={"Authorization": f"Bearer {manager_pair['access_token']}"}
        )
        assert resp.status_code == 401


class TestDeactivationBumpsTokenVersion:
    async def test_managers_old_token_stops_working_after_deactivation(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str, manager: uuid.UUID,
        manager_password: str,
    ) -> None:
        owner_pair = await _login(client, "owner@test.lk", owner_password)
        manager_pair = await _login(client, "manager@test.lk", manager_password)

        patch = await client.patch(
            f"/users/{manager}",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {owner_pair['access_token']}"},
        )
        assert patch.status_code == 200
        assert patch.json()["is_active"] is False

        resp = await client.get(
            "/me", headers={"Authorization": f"Bearer {manager_pair['access_token']}"}
        )
        assert resp.status_code == 401

        # A deactivated user cannot log in again either.
        login = await client.post(
            "/auth/login",
            json={
                "email": "manager@test.lk",
                "password": manager_password,
                "device_id": "d2",
            },
        )
        assert login.status_code == 401


class TestUserCrud:
    async def test_owner_lists_and_creates_users(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        owner_pair = await _login(client, "owner@test.lk", owner_password)
        headers = {"Authorization": f"Bearer {owner_pair['access_token']}"}

        create = await client.post(
            "/users",
            json={
                "email": "new-hire@test.lk",
                "password": "a-strong-enough-password",
                "full_name": "New Hire",
                "role": "MANAGER",
            },
            headers=headers,
        )
        assert create.status_code == 201
        assert create.json()["email"] == "new-hire@test.lk"

        listing = await client.get("/users", headers=headers)
        assert listing.status_code == 200
        emails = {u["email"] for u in listing.json()}
        assert emails == {"owner@test.lk", "new-hire@test.lk"}

    async def test_patching_an_unknown_user_is_404_not_403(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        owner_pair = await _login(client, "owner@test.lk", owner_password)
        resp = await client.patch(
            f"/users/{uuid.uuid4()}",
            json={"full_name": "Nobody"},
            headers={"Authorization": f"Bearer {owner_pair['access_token']}"},
        )
        assert resp.status_code == 404

    async def test_role_change_writes_an_audit_row_with_old_and_new_data(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        manager: uuid.UUID,
        session: AsyncSession,
        company: uuid.UUID,
    ) -> None:
        owner_pair = await _login(client, "owner@test.lk", owner_password)
        await client.patch(
            f"/users/{manager}",
            json={"role": "OWNER"},
            headers={"Authorization": f"Bearer {owner_pair['access_token']}"},
        )

        row = (
            await session.execute(
                text(
                    "SELECT old_data, new_data FROM audit_logs "
                    "WHERE company_id = :cid AND action = 'USER_UPDATE' AND entity_id = :uid"
                ),
                {"cid": str(company), "uid": str(manager)},
            )
        ).one()
        assert row.old_data["role"] == "MANAGER"
        assert row.new_data["role"] == "OWNER"


class TestDuplicateEmailIsRejectedCleanly:
    """A duplicate email used to be an uncaught `IntegrityError` — a bare
    500 with no `detail` Flutter could show. `create_user` now pre-checks
    and also catches the constraint violation itself, so this is always a
    clean 409, never a 500."""

    async def test_duplicate_email_is_409_not_500(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        owner_pair = await _login(client, "owner@test.lk", owner_password)
        headers = {"Authorization": f"Bearer {owner_pair['access_token']}"}
        payload = {
            "email": "duplicate@test.lk",
            "password": "a-strong-enough-password",
            "full_name": "First",
            "role": "MANAGER",
        }

        first = await client.post("/users", json=payload, headers=headers)
        assert first.status_code == 201, first.text

        second = await client.post(
            "/users", json={**payload, "full_name": "Second"}, headers=headers
        )
        assert second.status_code == 409, second.text
        assert second.json()["code"] == "EMAIL_ALREADY_EXISTS"

    async def test_duplicate_email_is_rejected_case_insensitively(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        owner_pair = await _login(client, "owner@test.lk", owner_password)
        headers = {"Authorization": f"Bearer {owner_pair['access_token']}"}

        first = await client.post(
            "/users",
            json={
                "email": "MixedCase@test.lk",
                "password": "a-strong-enough-password",
                "full_name": "First",
                "role": "MANAGER",
            },
            headers=headers,
        )
        assert first.status_code == 201, first.text

        second = await client.post(
            "/users",
            json={
                "email": "mixedcase@test.lk",
                "password": "a-strong-enough-password",
                "full_name": "Second",
                "role": "MANAGER",
            },
            headers=headers,
        )
        assert second.status_code == 409, second.text
        assert second.json()["code"] == "EMAIL_ALREADY_EXISTS"

    async def test_the_same_email_in_a_different_company_is_allowed(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        session: AsyncSession,
    ) -> None:
        """The constraint is per-tenant (`company_id`, `email`), not global —
        this must stay true; two unrelated shops can both have a manager
        named the same email address."""
        other_company = uuid.uuid4()
        await session.execute(
            text("INSERT INTO companies (id, name) VALUES (:id, 'Other Supermarket')"),
            {"id": str(other_company)},
        )
        await session.execute(
            text(
                "INSERT INTO users (id, company_id, email, full_name, password_hash, role) "
                "VALUES (:id, :cid, 'shared@test.lk', 'Existing Elsewhere', 'x', 'MANAGER')"
            ),
            {"id": str(uuid.uuid4()), "cid": str(other_company)},
        )
        await session.commit()

        owner_pair = await _login(client, "owner@test.lk", owner_password)
        headers = {"Authorization": f"Bearer {owner_pair['access_token']}"}
        resp = await client.post(
            "/users",
            json={
                "email": "shared@test.lk",
                "password": "a-strong-enough-password",
                "full_name": "Same Email, Different Shop",
                "role": "MANAGER",
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

    async def test_concurrent_creation_of_the_same_email_yields_one_201_and_one_409(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """Closes the race the pre-check alone can't: two requests for the
        same email both reaching the SELECT before either INSERTs. Neither
        must ever surface as a 500."""
        owner_pair = await _login(client, "owner@test.lk", owner_password)
        headers = {"Authorization": f"Bearer {owner_pair['access_token']}"}
        payload = {
            "email": "racing@test.lk",
            "password": "a-strong-enough-password",
            "full_name": "Racer",
            "role": "MANAGER",
        }

        responses = await asyncio.gather(
            client.post("/users", json=payload, headers=headers),
            client.post("/users", json=payload, headers=headers),
        )
        statuses = sorted(r.status_code for r in responses)
        assert statuses == [201, 409], [r.text for r in responses]
        conflict = next(r for r in responses if r.status_code == 409)
        assert conflict.json()["code"] == "EMAIL_ALREADY_EXISTS"
