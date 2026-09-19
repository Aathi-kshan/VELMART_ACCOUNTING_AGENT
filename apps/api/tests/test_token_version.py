"""Bumping token_version invalidates every outstanding access token instantly
(plan section 20.2) — this is what makes a role change or deactivation take
effect immediately rather than waiting for the token to expire.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class TestTokenVersion:
    async def test_valid_token_works_before_any_bump(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        pair = (
            await client.post(
                "/auth/login",
                json={
                    "email": "owner@test.lk",
                    "password": owner_password,
                    "device_id": "d1",
                },
            )
        ).json()

        resp = await client.get(
            "/me", headers={"Authorization": f"Bearer {pair['access_token']}"}
        )
        assert resp.status_code == 200

    async def test_bumped_version_invalidates_an_unexpired_token(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str, session: AsyncSession
    ) -> None:
        pair = (
            await client.post(
                "/auth/login",
                json={
                    "email": "owner@test.lk",
                    "password": owner_password,
                    "device_id": "d1",
                },
            )
        ).json()

        # Simulate a role change / deactivation elsewhere in the system.
        await session.execute(
            text("UPDATE users SET token_version = token_version + 1 WHERE id = :id"),
            {"id": str(owner)},
        )
        await session.commit()

        resp = await client.get(
            "/me", headers={"Authorization": f"Bearer {pair['access_token']}"}
        )
        assert resp.status_code == 401

    async def test_missing_token_is_401(self, client: AsyncClient) -> None:
        resp = await client.get("/me")
        assert resp.status_code == 401

    async def test_garbage_token_is_401(self, client: AsyncClient) -> None:
        resp = await client.get(
            "/me", headers={"Authorization": "Bearer not-a-jwt-at-all"}
        )
        assert resp.status_code == 401
