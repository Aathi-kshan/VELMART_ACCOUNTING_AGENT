"""Postgres-backed rate limiting (plan sections 5.3, 20.3)."""

from __future__ import annotations

from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import LOGIN_LIMIT_PER_MINUTE, hit, hit_login_ip, purge_expired


class TestUnitBehaviour:
    async def test_allows_up_to_the_limit(self, session: AsyncSession) -> None:
        for i in range(5):
            result = await hit(session, bucket_key="test:x", limit=5)
            assert result.allowed, f"request {i + 1} should be allowed"
        await session.commit()

    async def test_refuses_beyond_the_limit(self, session: AsyncSession) -> None:
        for _ in range(5):
            await hit(session, bucket_key="test:y", limit=5)
        sixth = await hit(session, bucket_key="test:y", limit=5)
        assert not sixth.allowed
        assert sixth.current_count == 6
        await session.commit()

    async def test_different_buckets_are_independent(self, session: AsyncSession) -> None:
        for _ in range(5):
            await hit(session, bucket_key="test:a", limit=5)
        # A different bucket starts fresh even though "a" is exhausted.
        result = await hit(session, bucket_key="test:b", limit=5)
        assert result.allowed
        await session.commit()

    async def test_new_window_resets_the_count(self, session: AsyncSession) -> None:
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        for _ in range(5):
            await hit(session, bucket_key="test:c", limit=5, now=base)

        from datetime import timedelta

        next_minute = base + timedelta(seconds=61)
        result = await hit(session, bucket_key="test:c", limit=5, now=next_minute)
        assert result.allowed, "a new window must not inherit the old count"
        await session.commit()

    async def test_purge_removes_old_windows_only(self, session: AsyncSession) -> None:
        old = datetime(2020, 1, 1, tzinfo=UTC)
        recent = datetime.now(tz=UTC)
        await hit(session, bucket_key="test:old", limit=100, now=old)
        await hit(session, bucket_key="test:recent", limit=100, now=recent)
        await session.commit()

        removed = await purge_expired(session, older_than_hours=24)
        await session.commit()
        assert removed == 1


class TestLoginEndpointThrottling:
    async def test_sixth_login_attempt_in_a_minute_is_refused(
        self, client: AsyncClient
    ) -> None:
        for i in range(LOGIN_LIMIT_PER_MINUTE):
            resp = await client.post(
                "/auth/login",
                json={
                    "email": "nobody@test.lk",
                    "password": "irrelevant",
                    "device_id": "d1",
                },
            )
            assert resp.status_code == 401, f"attempt {i + 1} should reach the auth check"

        sixth = await client.post(
            "/auth/login",
            json={"email": "nobody@test.lk", "password": "irrelevant", "device_id": "d1"},
        )
        assert sixth.status_code == 429
        assert "Retry-After" in sixth.headers

    async def test_throttle_applies_before_checking_credentials(
        self, client: AsyncClient
    ) -> None:
        """Even a request with no matching account still consumes the bucket —
        the throttle must not depend on whether the account exists, or an
        attacker could distinguish valid emails by which one gets rate limited
        first."""
        for _ in range(LOGIN_LIMIT_PER_MINUTE):
            await client.post(
                "/auth/login",
                json={
                    "email": f"random-{_}@test.lk",
                    "password": "x",
                    "device_id": "d1",
                },
            )
        resp = await client.post(
            "/auth/login",
            json={"email": "yet-another@test.lk", "password": "x", "device_id": "d1"},
        )
        assert resp.status_code == 429


class TestLoginRateLimitHelper:
    async def test_hit_login_ip_uses_the_configured_limit(
        self, session: AsyncSession
    ) -> None:
        for _ in range(LOGIN_LIMIT_PER_MINUTE):
            result = await hit_login_ip(session, "203.0.113.5")
        assert result.allowed
        overflow = await hit_login_ip(session, "203.0.113.5")
        assert not overflow.allowed
        await session.commit()
