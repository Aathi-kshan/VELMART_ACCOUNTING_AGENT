"""Postgres-backed idempotency (plan sections 5.3, 21.1)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.idempotency import (
    IdempotencyConflictError,
    hash_request,
    lookup,
    purge_expired,
    reserve,
    store_response,
)


class TestHashing:
    def test_same_payload_same_hash(self) -> None:
        assert hash_request({"a": 1, "b": 2}) == hash_request({"a": 1, "b": 2})

    def test_key_order_does_not_matter(self) -> None:
        assert hash_request({"a": 1, "b": 2}) == hash_request({"b": 2, "a": 1})

    def test_different_payload_different_hash(self) -> None:
        assert hash_request({"a": 1}) != hash_request({"a": 2})


class TestReserveAndReplay:
    async def test_first_reservation_succeeds(self, session: AsyncSession, owner) -> None:
        won = await reserve(
            session, key="k1", user_id=owner, endpoint="/pages/1/records", request_hash="h1"
        )
        assert won is True
        await session.commit()

    async def test_second_reservation_of_the_same_key_loses(
        self, session: AsyncSession, owner
    ) -> None:
        await reserve(
            session, key="k2", user_id=owner, endpoint="/pages/1/records", request_hash="h1"
        )
        again = await reserve(
            session, key="k2", user_id=owner, endpoint="/pages/1/records", request_hash="h1"
        )
        assert again is False
        await session.commit()

    async def test_replay_with_same_body_returns_the_stored_response(
        self, session: AsyncSession, owner
    ) -> None:
        key, endpoint, body_hash = "k3", "/pages/1/records", "h1"
        await reserve(session, key=key, user_id=owner, endpoint=endpoint, request_hash=body_hash)
        await store_response(session, key=key, status_code=201, body={"id": "abc"})
        await session.commit()

        stored = await lookup(session, key=key, endpoint=endpoint, request_hash=body_hash)
        assert stored is not None
        assert stored.status_code == 201
        assert stored.body == {"id": "abc"}

    async def test_replay_with_different_body_conflicts(
        self, session: AsyncSession, owner
    ) -> None:
        key, endpoint = "k4", "/pages/1/records"
        await reserve(session, key=key, user_id=owner, endpoint=endpoint, request_hash="h1")
        await store_response(session, key=key, status_code=201, body={"id": "abc"})
        await session.commit()

        import pytest

        with pytest.raises(IdempotencyConflictError):
            await lookup(session, key=key, endpoint=endpoint, request_hash="different-hash")

    async def test_unknown_key_returns_none(self, session: AsyncSession) -> None:
        result = await lookup(
            session, key="never-used", endpoint="/x", request_hash="h"
        )
        assert result is None

    async def test_in_flight_key_conflicts_rather_than_hanging(
        self, session: AsyncSession, owner
    ) -> None:
        """A key that has been reserved but not yet completed (status_code is
        still NULL) means an identical request is mid-flight — surfaced as a
        conflict, not a false "not found"."""
        key, endpoint, body_hash = "k5", "/pages/1/records", "h1"
        await reserve(session, key=key, user_id=owner, endpoint=endpoint, request_hash=body_hash)
        await session.commit()

        import pytest

        with pytest.raises(IdempotencyConflictError, match="being processed"):
            await lookup(session, key=key, endpoint=endpoint, request_hash=body_hash)


class TestPurge:
    async def test_purge_removes_old_keys_only(
        self, session: AsyncSession, owner
    ) -> None:
        from sqlalchemy import text

        await reserve(session, key="old-key", user_id=owner, endpoint="/x", request_hash="h")
        await reserve(session, key="new-key", user_id=owner, endpoint="/x", request_hash="h")
        await session.execute(
            text(
                "UPDATE idempotency_keys SET created_at = now() - interval '49 hours' "
                "WHERE key = 'old-key'"
            )
        )
        await session.commit()

        removed = await purge_expired(session, older_than_hours=48)
        await session.commit()
        assert removed == 1
