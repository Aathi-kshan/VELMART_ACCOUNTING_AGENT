"""The throttles that existed in config but were never applied.

`RATE_LIMIT_PER_MINUTE` was a setting and `ratelimit.hit_api_user` was a
written, working helper — with **zero call sites**. There was no per-user API
throttle at all, so `/auth/refresh`, `/auth/logout` and every authenticated
endpoint could be called without limit.

Separately, `_client_ip` read `request.client.host` and nothing else. Behind
a reverse proxy (Railway terminates TLS in front of this app) every request
arrives from the proxy, so the login limiter put the entire deployment into a
single bucket: five failed logins from anyone locked out every user, and the
per-attacker limit vanished. The header cannot simply be trusted either —
`X-Forwarded-For` is client-supplied, and honouring it unconditionally lets a
caller forge a fresh IP per request and evade the limit completely. Hence
`TRUSTED_PROXY_HOPS`, which is 0 by default.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.config import get_settings


@pytest.fixture(autouse=True)
def _restore_settings():  # noqa: ANN202
    """These tests change settings, which are cached process-wide."""
    yield
    get_settings.cache_clear()


async def _login(client: AsyncClient, owner_password: str) -> str:
    resp = await client.post(
        "/auth/login",
        json={"email": "owner@test.lk", "password": owner_password, "device_id": "d1"},
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


class TestPerUserApiThrottle:
    async def test_it_is_actually_applied(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Set the limit low and confirm a 429 arrives — before this wiring
        the helper was never called, so no number of requests was ever
        refused."""
        token = await _login(client, owner_password)
        headers = {"Authorization": f"Bearer {token}"}

        settings = get_settings()
        monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 3, raising=False)

        statuses = []
        for _ in range(6):
            resp = await client.get("/me", headers=headers)
            statuses.append(resp.status_code)

        assert 429 in statuses, f"the per-user throttle never fired: {statuses}"
        # Everything before the limit must still have worked.
        assert statuses[0] == 200

    async def test_the_response_says_when_to_retry(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        token = await _login(client, owner_password)
        headers = {"Authorization": f"Bearer {token}"}
        monkeypatch.setattr(get_settings(), "RATE_LIMIT_PER_MINUTE", 1, raising=False)

        last = None
        for _ in range(4):
            last = await client.get("/me", headers=headers)
        assert last is not None
        assert last.status_code == 429, last.text
        assert last.json()["code"] == "RATE_LIMITED"
        assert "Retry-After" in last.headers

    async def test_the_default_limit_does_not_disturb_ordinary_use(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """A guard against making the app unusable: a normal burst of
        requests must pass under the shipped default."""
        token = await _login(client, owner_password)
        headers = {"Authorization": f"Bearer {token}"}
        for _ in range(20):
            resp = await client.get("/me", headers=headers)
            assert resp.status_code == 200, resp.text


class TestLoginIpResolution:
    async def test_forwarded_header_is_ignored_by_default(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """With no trusted proxy configured, a client cannot pick its own
        rate-limit bucket by sending the header."""
        get_settings.cache_clear()
        assert get_settings().TRUSTED_PROXY_HOPS == 0

        # Exhaust the login bucket with deliberately wrong credentials.
        for _ in range(8):
            await client.post(
                "/auth/login",
                json={"email": "owner@test.lk", "password": "wrong", "device_id": "d1"},
            )

        # A forged header must not hand out a fresh bucket.
        resp = await client.post(
            "/auth/login",
            json={"email": "owner@test.lk", "password": "wrong", "device_id": "d1"},
            headers={"X-Forwarded-For": "203.0.113.9"},
        )
        assert resp.status_code == 429, (
            "a client escaped the login limiter with a forged X-Forwarded-For"
        )

    async def test_a_trusted_proxy_separates_clients(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With one trusted hop, two real clients behind the same proxy get
        their own buckets instead of sharing the deployment's."""
        monkeypatch.setattr(get_settings(), "TRUSTED_PROXY_HOPS", 1, raising=False)

        for _ in range(8):
            await client.post(
                "/auth/login",
                json={"email": "owner@test.lk", "password": "wrong", "device_id": "d1"},
                headers={"X-Forwarded-For": "198.51.100.1"},
            )
        blocked = await client.post(
            "/auth/login",
            json={"email": "owner@test.lk", "password": "wrong", "device_id": "d1"},
            headers={"X-Forwarded-For": "198.51.100.1"},
        )
        assert blocked.status_code == 429, blocked.text

        # A different client behind the same proxy must have its own bucket.
        # It will still be refused — eight wrong passwords also tripped the
        # per-account lockout, which is a separate mechanism and deliberately
        # not IP-scoped — so the meaningful assertion is that it is *not*
        # rate-limited, i.e. it was never put in the first client's bucket.
        other = await client.post(
            "/auth/login",
            json={"email": "owner@test.lk", "password": owner_password, "device_id": "d2"},
            headers={"X-Forwarded-For": "198.51.100.2"},
        )
        assert other.status_code != 429, (
            f"one client's failures consumed another client's rate limit: {other.text}"
        )
