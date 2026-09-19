"""Login, lockout, and non-enumeration (plan section 20.2)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.usefixtures("owner")


async def _login(
    client: AsyncClient, email: str, password: str, device: str = "test-device"
) -> Response:
    return await client.post(
        "/auth/login",
        json={"email": email, "password": password, "device_id": device},
    )


class TestSuccessfulLogin:
    async def test_returns_a_token_pair(
        self, client: AsyncClient, owner_password: str
    ) -> None:
        resp = await _login(client, "owner@test.lk", owner_password)
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 15 * 60
        assert body["access_token"] and body["refresh_token"]
        assert body["user"]["role"] == "OWNER"

    async def test_never_returns_the_password_hash(
        self, client: AsyncClient, owner_password: str
    ) -> None:
        resp = await _login(client, "owner@test.lk", owner_password)
        assert "password" not in resp.text.lower()

    async def test_refresh_token_is_stored_only_as_a_hash(
        self, client: AsyncClient, owner_password: str, session: AsyncSession
    ) -> None:
        resp = await _login(client, "owner@test.lk", owner_password)
        raw = resp.json()["refresh_token"]

        result = await session.execute(text("SELECT token_hash FROM refresh_tokens"))
        stored = result.scalars().all()
        assert stored, "a refresh token row should exist"
        assert raw not in stored, "the raw token must never be stored"

    async def test_resets_failed_attempts(
        self, client: AsyncClient, owner_password: str, session: AsyncSession, owner: uuid.UUID
    ) -> None:
        await _login(client, "owner@test.lk", "wrong-password-here")
        await _login(client, "owner@test.lk", owner_password)

        attempts = (
            await session.execute(
                text("SELECT failed_attempts FROM users WHERE id = :id"), {"id": str(owner)}
            )
        ).scalar_one()
        assert attempts == 0


class TestFailedLogin:
    async def test_wrong_password_is_401(self, client: AsyncClient) -> None:
        resp = await _login(client, "owner@test.lk", "definitely-wrong")
        assert resp.status_code == 401

    async def test_unknown_email_is_indistinguishable_from_wrong_password(
        self, client: AsyncClient
    ) -> None:
        """The endpoint must not reveal whether an account exists."""
        unknown = await _login(client, "nobody@test.lk", "definitely-wrong")
        wrong = await _login(client, "owner@test.lk", "definitely-wrong")

        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()["detail"] == wrong.json()["detail"]
        assert unknown.json()["code"] == wrong.json()["code"]

    async def test_increments_the_counter(
        self, client: AsyncClient, session: AsyncSession, owner: uuid.UUID
    ) -> None:
        await _login(client, "owner@test.lk", "definitely-wrong")
        await _login(client, "owner@test.lk", "definitely-wrong")

        attempts = (
            await session.execute(
                text("SELECT failed_attempts FROM users WHERE id = :id"), {"id": str(owner)}
            )
        ).scalar_one()
        assert attempts == 2

    async def test_audits_the_failure(
        self, client: AsyncClient, session: AsyncSession
    ) -> None:
        await _login(client, "owner@test.lk", "definitely-wrong")
        actions = (
            await session.execute(text("SELECT action FROM audit_logs"))
        ).scalars().all()
        assert "LOGIN_FAILED" in actions


class TestLockout:
    async def test_locks_after_five_failures(
        self,
        client: AsyncClient,
        session: AsyncSession,
        owner: uuid.UUID,
    ) -> None:
        for _ in range(5):
            await _login(client, "owner@test.lk", "definitely-wrong")

        locked_until = (
            await session.execute(
                text("SELECT locked_until FROM users WHERE id = :id"), {"id": str(owner)}
            )
        ).scalar_one()
        assert locked_until is not None, "account should be locked after 5 failures"

    async def test_locked_account_refuses_the_correct_password(
        self,
        session: AsyncSession,
        owner: uuid.UUID,
        owner_password: str,
    ) -> None:
        """Isolated at the service layer: the login-IP limiter (5/min) shares
        its threshold with the lockout count (5 attempts), so driving this
        through the HTTP endpoint would hit rate limiting first rather than
        proving the lock itself. See test_rate_limit.py for that mechanism.
        """
        from app.services import auth_service

        await session.execute(
            text(
                "UPDATE users SET locked_until = now() + interval '15 minutes' "
                "WHERE id = :id"
            ),
            {"id": str(owner)},
        )
        await session.commit()

        with pytest.raises(auth_service.AccountLockedError):
            await auth_service.login(
                session,
                email="owner@test.lk",
                password=owner_password,
                device_id="test-device",
            )

    async def test_four_failures_do_not_lock(
        self, client: AsyncClient, session: AsyncSession, owner: uuid.UUID
    ) -> None:
        for _ in range(4):
            await _login(client, "owner@test.lk", "definitely-wrong")

        locked_until = (
            await session.execute(
                text("SELECT locked_until FROM users WHERE id = :id"), {"id": str(owner)}
            )
        ).scalar_one()
        assert locked_until is None


class TestInactiveAccount:
    async def test_deactivated_user_cannot_log_in(
        self, client: AsyncClient, session: AsyncSession, owner: uuid.UUID, owner_password: str
    ) -> None:
        await session.execute(
            text("UPDATE users SET is_active = FALSE WHERE id = :id"), {"id": str(owner)}
        )
        await session.commit()

        resp = await _login(client, "owner@test.lk", owner_password)
        assert resp.status_code == 401
