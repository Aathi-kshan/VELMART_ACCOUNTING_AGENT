"""Refresh rotation and replay detection (plan section 20.2)."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _login(client: AsyncClient, email: str, password: str) -> dict:
    resp = await client.post(
        "/auth/login",
        json={"email": email, "password": password, "device_id": "device-a"},
    )
    assert resp.status_code == 200
    return resp.json()


class TestRotation:
    async def test_refresh_issues_a_new_pair(
        self, client: AsyncClient, owner, owner_password: str
    ) -> None:
        first = await _login(client, "owner@test.lk", owner_password)

        resp = await client.post(
            "/auth/refresh", json={"refresh_token": first["refresh_token"]}
        )
        assert resp.status_code == 200
        second = resp.json()
        assert second["refresh_token"] != first["refresh_token"]
        assert second["access_token"] != first["access_token"]

    async def test_old_token_is_revoked_and_linked(
        self, client: AsyncClient, owner, owner_password: str, session: AsyncSession
    ) -> None:
        first = await _login(client, "owner@test.lk", owner_password)
        await client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})

        row = (
            await session.execute(
                text(
                    "SELECT revoked_at, replaced_by FROM refresh_tokens "
                    "ORDER BY created_at LIMIT 1"
                )
            )
        ).one()
        assert row.revoked_at is not None
        assert row.replaced_by is not None

    async def test_new_access_token_still_works(
        self, client: AsyncClient, owner, owner_password: str
    ) -> None:
        first = await _login(client, "owner@test.lk", owner_password)
        refreshed = (
            await client.post(
                "/auth/refresh", json={"refresh_token": first["refresh_token"]}
            )
        ).json()

        resp = await client.get(
            "/me", headers={"Authorization": f"Bearer {refreshed['access_token']}"}
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "OWNER"


class TestReplayDetection:
    async def test_replaying_a_rotated_token_is_refused(
        self, client: AsyncClient, owner, owner_password: str
    ) -> None:
        first = await _login(client, "owner@test.lk", owner_password)
        await client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})

        # The original token has now been rotated away. Presenting it again
        # is a replay.
        replay = await client.post(
            "/auth/refresh", json={"refresh_token": first["refresh_token"]}
        )
        assert replay.status_code == 401

    async def test_replay_revokes_the_whole_device_family(
        self, client: AsyncClient, owner, owner_password: str, session: AsyncSession
    ) -> None:
        first = await _login(client, "owner@test.lk", owner_password)
        second_resp = await client.post(
            "/auth/refresh", json={"refresh_token": first["refresh_token"]}
        )
        second = second_resp.json()

        # Replay the stale token — this must revoke the *current* valid token
        # too, since the device is now assumed compromised.
        await client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})

        still_valid = (
            await session.execute(
                text(
                    "SELECT count(*) FROM refresh_tokens "
                    "WHERE user_id = :uid AND device_id = 'device-a' "
                    "AND revoked_at IS NULL"
                ),
                {"uid": str(owner)},
            )
        ).scalar_one()
        assert still_valid == 0, "every token for the device must be revoked"

        # The token issued by the second (legitimate) refresh no longer works.
        resp = await client.post(
            "/auth/refresh", json={"refresh_token": second["refresh_token"]}
        )
        assert resp.status_code == 401

    async def test_replay_is_audited(
        self, client: AsyncClient, owner, owner_password: str, session: AsyncSession
    ) -> None:
        first = await _login(client, "owner@test.lk", owner_password)
        await client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
        await client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})

        actions = (
            await session.execute(text("SELECT action FROM audit_logs"))
        ).scalars().all()
        assert "LOGIN_FAILED" in actions


class TestInvalidTokens:
    async def test_unknown_token_is_refused(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/auth/refresh", json={"refresh_token": "not-a-real-token"}
        )
        assert resp.status_code == 401

    async def test_expired_token_is_refused(
        self, client: AsyncClient, owner, owner_password: str, session: AsyncSession
    ) -> None:
        pair = await _login(client, "owner@test.lk", owner_password)
        await session.execute(
            text("UPDATE refresh_tokens SET expires_at = now() - interval '1 day'")
        )
        await session.commit()

        resp = await client.post(
            "/auth/refresh", json={"refresh_token": pair["refresh_token"]}
        )
        assert resp.status_code == 401


class TestLogout:
    async def test_logout_revokes_the_token(
        self, client: AsyncClient, owner, owner_password: str, session: AsyncSession
    ) -> None:
        pair = await _login(client, "owner@test.lk", owner_password)

        resp = await client.post(
            "/auth/logout", json={"refresh_token": pair["refresh_token"]}
        )
        assert resp.status_code == 204

        revoked = (
            await session.execute(text("SELECT revoked_at FROM refresh_tokens"))
        ).scalar_one()
        assert revoked is not None

    async def test_logout_is_idempotent_for_unknown_tokens(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/auth/logout", json={"refresh_token": "never-issued"}
        )
        assert resp.status_code == 204
