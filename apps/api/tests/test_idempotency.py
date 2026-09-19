"""Postgres-backed idempotency (plan sections 5.3, 21.1).

Keys are scoped per company (migration 0017). They were global — a key
string is client-supplied, so one company could replay another company's
stored response body, or be blocked by another company's key. Every call
below therefore passes `company_id`, and `TestKeysAreScopedPerCompany`
holds that boundary.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
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
    async def test_first_reservation_succeeds(
        self, session: AsyncSession, company: uuid.UUID, owner: uuid.UUID
    ) -> None:
        won = await reserve(
            session,
            company_id=company,
            key="k1",
            user_id=owner,
            endpoint="/pages/1/records",
            request_hash="h1",
        )
        assert won is True
        await session.commit()

    async def test_second_reservation_of_the_same_key_loses(
        self, session: AsyncSession, company: uuid.UUID, owner: uuid.UUID
    ) -> None:
        await reserve(
            session,
            company_id=company,
            key="k2",
            user_id=owner,
            endpoint="/pages/1/records",
            request_hash="h1",
        )
        again = await reserve(
            session,
            company_id=company,
            key="k2",
            user_id=owner,
            endpoint="/pages/1/records",
            request_hash="h1",
        )
        assert again is False
        await session.commit()

    async def test_replay_with_same_body_returns_the_stored_response(
        self, session: AsyncSession, company: uuid.UUID, owner: uuid.UUID
    ) -> None:
        key, endpoint, body_hash = "k3", "/pages/1/records", "h1"
        await reserve(
            session,
            company_id=company,
            key=key,
            user_id=owner,
            endpoint=endpoint,
            request_hash=body_hash,
        )
        await store_response(
            session, company_id=company, key=key, status_code=201, body={"id": "abc"}
        )
        await session.commit()

        stored = await lookup(
            session, company_id=company, key=key, endpoint=endpoint, request_hash=body_hash
        )
        assert stored is not None
        assert stored.status_code == 201
        assert stored.body == {"id": "abc"}

    async def test_replay_with_different_body_conflicts(
        self, session: AsyncSession, company: uuid.UUID, owner: uuid.UUID
    ) -> None:
        key, endpoint = "k4", "/pages/1/records"
        await reserve(
            session,
            company_id=company,
            key=key,
            user_id=owner,
            endpoint=endpoint,
            request_hash="h1",
        )
        await store_response(
            session, company_id=company, key=key, status_code=201, body={"id": "abc"}
        )
        await session.commit()

        with pytest.raises(IdempotencyConflictError):
            await lookup(
                session,
                company_id=company,
                key=key,
                endpoint=endpoint,
                request_hash="different-hash",
            )

    async def test_unknown_key_returns_none(
        self, session: AsyncSession, company: uuid.UUID
    ) -> None:
        result = await lookup(
            session, company_id=company, key="never-used", endpoint="/x", request_hash="h"
        )
        assert result is None

    async def test_in_flight_key_conflicts_rather_than_hanging(
        self, session: AsyncSession, company: uuid.UUID, owner: uuid.UUID
    ) -> None:
        """A key that has been reserved but not yet completed (status_code is
        still NULL) means an identical request is mid-flight — surfaced as a
        conflict, not a false "not found"."""
        key, endpoint, body_hash = "k5", "/pages/1/records", "h1"
        await reserve(
            session,
            company_id=company,
            key=key,
            user_id=owner,
            endpoint=endpoint,
            request_hash=body_hash,
        )
        await session.commit()

        with pytest.raises(IdempotencyConflictError, match="being processed"):
            await lookup(
                session, company_id=company, key=key, endpoint=endpoint, request_hash=body_hash
            )


class TestKeysAreScopedPerCompany:
    """The boundary migration 0017 introduced.

    `idempotency_keys` is deliberately excluded from RLS, so nothing below
    the application enforces this — these are the only tests standing
    between one tenant and another tenant's stored response body.
    """

    @staticmethod
    async def _other_company(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
        """A second company with its own owner, built directly so this does
        not depend on the shared `company`/`owner` fixtures."""
        from app.core.security import hash_password

        company_id, user_id = uuid.uuid4(), uuid.uuid4()
        await session.execute(
            text("INSERT INTO companies (id, name) VALUES (:id, 'Other Traders')"),
            {"id": str(company_id)},
        )
        await session.execute(
            text(
                """
                INSERT INTO users (id, company_id, email, full_name, password_hash, role)
                VALUES (:id, :company_id, :email, 'Other Owner', :pw, 'OWNER')
                """
            ),
            {
                "id": str(user_id),
                "company_id": str(company_id),
                "email": "owner@other.lk",
                "pw": hash_password("correct-horse-battery"),
            },
        )
        await session.commit()
        return company_id, user_id

    async def test_another_company_cannot_read_a_stored_response(
        self, session: AsyncSession, company: uuid.UUID, owner: uuid.UUID
    ) -> None:
        """The leak itself: same key, same endpoint, same body hash, and the
        other tenant used to get this company's response body back."""
        key, endpoint, body_hash = "shared-key", "/pages/1/records", "same-hash"
        await reserve(
            session,
            company_id=company,
            key=key,
            user_id=owner,
            endpoint=endpoint,
            request_hash=body_hash,
        )
        await store_response(
            session,
            company_id=company,
            key=key,
            status_code=201,
            body={"id": "secret-record", "data": {"amount": "999999.00"}},
        )
        await session.commit()

        other_company, _ = await self._other_company(session)
        leaked = await lookup(
            session, company_id=other_company, key=key, endpoint=endpoint, request_hash=body_hash
        )
        assert leaked is None, f"another company read this company's response: {leaked}"

    async def test_two_companies_can_use_the_same_key_string(
        self, session: AsyncSession, company: uuid.UUID, owner: uuid.UUID
    ) -> None:
        """The other half: a globally unique key also meant one company's key
        could block another company's unrelated request with a 409."""
        key, endpoint = "collide", "/pages/1/records"
        first = await reserve(
            session,
            company_id=company,
            key=key,
            user_id=owner,
            endpoint=endpoint,
            request_hash="h1",
        )
        assert first is True

        other_company, other_owner = await self._other_company(session)
        second = await reserve(
            session,
            company_id=other_company,
            key=key,
            user_id=other_owner,
            endpoint=endpoint,
            request_hash="h2",
        )
        assert second is True, "another company's key blocked this one"
        await session.commit()

    async def test_storing_a_response_does_not_touch_another_companys_row(
        self, session: AsyncSession, company: uuid.UUID, owner: uuid.UUID
    ) -> None:
        """`store_response` is an UPDATE keyed on the same pair; unscoped it
        would have written over every company's row sharing that key."""
        key, endpoint = "shared", "/pages/1/records"
        other_company, other_owner = await self._other_company(session)
        await reserve(
            session,
            company_id=company,
            key=key,
            user_id=owner,
            endpoint=endpoint,
            request_hash="h",
        )
        await reserve(
            session,
            company_id=other_company,
            key=key,
            user_id=other_owner,
            endpoint=endpoint,
            request_hash="h",
        )
        await store_response(
            session, company_id=company, key=key, status_code=201, body={"id": "mine"}
        )
        await session.commit()

        # The other company's row must still be in flight, not carrying our body.
        row = await session.execute(
            text(
                "SELECT response_body FROM idempotency_keys "
                "WHERE company_id = :company_id AND key = :key"
            ),
            {"company_id": str(other_company), "key": key},
        )
        assert row.scalar_one() is None


class TestPurge:
    async def test_purge_removes_old_keys_only(
        self, session: AsyncSession, company: uuid.UUID, owner: uuid.UUID
    ) -> None:
        await reserve(
            session,
            company_id=company,
            key="old-key",
            user_id=owner,
            endpoint="/x",
            request_hash="h",
        )
        await reserve(
            session,
            company_id=company,
            key="new-key",
            user_id=owner,
            endpoint="/x",
            request_hash="h",
        )
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
