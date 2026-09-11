"""Postgres-backed rate limiting (plan sections 5.3, 20.3).

No Redis: at three users the table will not become a bottleneck, and §23.6 makes
"measured contention on rate limiting" the trigger for revisiting that.

A fixed window rather than a sliding one — simpler, one row per bucket per
window, and the imprecision at a window boundary does not matter for limits
whose purpose is stopping brute force and runaway clients.

    login:ip:<addr>    5 / minute   (section 20.3)
    api:user:<uuid>    100 / minute
    ai:user:<uuid>     20 / 5 minutes
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncSession

LOGIN_LIMIT_PER_MINUTE = 5
AI_MESSAGES_PER_5_MIN = 20


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    current_count: int
    limit: int
    retry_after_seconds: int


def _window_start(now: datetime, window_seconds: int) -> datetime:
    """Truncate `now` to the start of its fixed window."""
    epoch_seconds = int(now.timestamp())
    return datetime.fromtimestamp(epoch_seconds - (epoch_seconds % window_seconds), tz=UTC)


async def hit(
    session: AsyncSession,
    *,
    bucket_key: str,
    limit: int,
    window_seconds: int = 60,
    now: datetime | None = None,
) -> RateLimitResult:
    """Count one request against a bucket and report whether it is allowed.

    The insert is atomic — `ON CONFLICT ... DO UPDATE` with the incremented
    count returned — so two concurrent requests cannot both read "4" and both
    decide they are the fifth.
    """
    now = now or datetime.now(tz=UTC)
    window = _window_start(now, window_seconds)

    result = await session.execute(
        text(
            """
            INSERT INTO rate_limits (bucket_key, window_start, request_count)
            VALUES (:bucket_key, :window_start, 1)
            ON CONFLICT (bucket_key, window_start)
            DO UPDATE SET request_count = rate_limits.request_count + 1
            RETURNING request_count
            """
        ),
        {"bucket_key": bucket_key, "window_start": window},
    )
    count = int(result.scalar_one())

    window_end = window + timedelta(seconds=window_seconds)
    return RateLimitResult(
        allowed=count <= limit,
        current_count=count,
        limit=limit,
        retry_after_seconds=max(1, int((window_end - now).total_seconds())),
    )


async def hit_login_ip(
    session: AsyncSession, ip_address: str, *, now: datetime | None = None
) -> RateLimitResult:
    """5 login attempts per minute per IP (plan section 20.3)."""
    return await hit(
        session,
        bucket_key=f"login:ip:{ip_address}",
        limit=LOGIN_LIMIT_PER_MINUTE,
        window_seconds=60,
        now=now,
    )


async def hit_api_user(
    session: AsyncSession, user_id: uuid.UUID, *, limit: int, now: datetime | None = None
) -> RateLimitResult:
    """Per-user API throttle; `limit` comes from RATE_LIMIT_PER_MINUTE."""
    return await hit(
        session,
        bucket_key=f"api:user:{user_id}",
        limit=limit,
        window_seconds=60,
        now=now,
    )


async def purge_expired(session: AsyncSession, *, older_than_hours: int = 24) -> int:
    """Drop stale windows. Called by the nightly maintenance job."""
    cutoff = datetime.now(tz=UTC) - timedelta(hours=older_than_hours)
    result = cast(
        CursorResult[Any],
        await session.execute(
            text("DELETE FROM rate_limits WHERE window_start < :cutoff"), {"cutoff": cutoff}
        ),
    )
    return result.rowcount or 0
