"""Postgres-backed idempotency (plan sections 5.3, 21.1).

Creates accept an `Idempotency-Key`. Replaying the same key with the same body
returns the stored response instead of creating a second row — which is what
makes the offline outbox safe to drain repeatedly (section 19.2: `client_uuid`
is the key end to end).

Replaying a key with a **different** body is a conflict, not a silent
overwrite: it means the client reused a key it should not have, and quietly
returning the old response would hide a real bug.

Rows older than 48h are removed by the nightly job (section 8.2).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncSession


class IdempotencyConflictError(Exception):
    """Same key, different request body."""


@dataclass(frozen=True, slots=True)
class StoredResponse:
    status_code: int
    body: Any


def hash_request(payload: Any) -> str:
    """A stable fingerprint of a request body.

    `sort_keys` so that a client reordering JSON fields is still recognised as
    the same request rather than a conflict.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def lookup(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    key: str,
    endpoint: str,
    request_hash: str,
) -> StoredResponse | None:
    """Return a previously stored response for this key, if any.

    Raises `IdempotencyConflictError` when the key was used for a different
    body — the caller should surface that as 409.

    `company_id` is part of the key's identity, not a filter added for
    safety. The key string comes from the client, so a global namespace let
    one company replay another company's stored response body, and let one
    company's key block another's request with a 409. See migration 0017.
    """
    result = await session.execute(
        text(
            """
            SELECT endpoint, request_hash, response_body, status_code
            FROM idempotency_keys
            WHERE company_id = :company_id AND key = :key
            """
        ),
        {"company_id": str(company_id), "key": key},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None

    if row["endpoint"] != endpoint or row["request_hash"] != request_hash:
        raise IdempotencyConflictError(
            "This Idempotency-Key was already used for a different request."
        )

    if row["status_code"] is None:
        # Reserved but not yet completed: an identical request is still in
        # flight. Treat as a conflict rather than returning a half-made answer.
        raise IdempotencyConflictError(
            "A request with this Idempotency-Key is still being processed."
        )

    return StoredResponse(status_code=row["status_code"], body=row["response_body"])


async def reserve(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    key: str,
    user_id: uuid.UUID,
    endpoint: str,
    request_hash: str,
) -> bool:
    """Claim a key before doing the work. False if another request won the race."""
    result = await session.execute(
        text(
            """
            INSERT INTO idempotency_keys (company_id, key, user_id, endpoint, request_hash)
            VALUES (:company_id, :key, :user_id, :endpoint, :request_hash)
            ON CONFLICT (company_id, key) DO NOTHING
            RETURNING key
            """
        ),
        {
            "company_id": str(company_id),
            "key": key,
            "user_id": user_id,
            "endpoint": endpoint,
            "request_hash": request_hash,
        },
    )
    return result.scalar_one_or_none() is not None


async def store_response(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    key: str,
    status_code: int,
    body: Any,
) -> None:
    """Record the outcome so a replay can return it."""
    await session.execute(
        text(
            """
            UPDATE idempotency_keys
            SET response_body = CAST(:body AS jsonb), status_code = :status_code
            WHERE company_id = :company_id AND key = :key
            """
        ),
        {
            "company_id": str(company_id),
            "key": key,
            "status_code": status_code,
            "body": json.dumps(body, default=str),
        },
    )


async def purge_expired(session: AsyncSession, *, older_than_hours: int = 48) -> int:
    """Delete keys older than 48h (plan section 8.2). Nightly job."""
    cutoff = datetime.now(tz=UTC) - timedelta(hours=older_than_hours)
    result = cast(
        CursorResult[Any],
        await session.execute(
            text("DELETE FROM idempotency_keys WHERE created_at < :cutoff"), {"cutoff": cutoff}
        ),
    )
    return result.rowcount or 0
