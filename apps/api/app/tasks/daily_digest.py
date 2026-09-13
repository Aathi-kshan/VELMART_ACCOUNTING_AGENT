"""Nightly daily digest (P5 §nightly-ops), scoped minimally per an explicit
decision made when planning this phase: one structured JSONB summary per
company per day, **no delivery mechanism** (no email/push channel exists
yet) — surfaced instead via `GET /dashboard/digest` and a small banner on
the audit screen (`app/services/dashboard_service.py`).

Runs over the `migrator` connection to summarize every company in one pass
rather than opening a separate RLS-scoped session per tenant.

Known simplification: `needs_review_count` only counts the generic
`records` table, not the six native business tables (which also carry
`needs_review` via `BusinessTableMixin`) — acceptable for a first pass at
a non-financial summary; revisit if the gap turns out to matter in
practice.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.migrator import get_migrator_session

_TRACKED_ACTIONS = (
    "RECORD_CREATE",
    "RECORD_UPDATE",
    "RECORD_DELETE",
    "DASHBOARD_WIDGET_CREATE",
)


@dataclass(frozen=True)
class DigestResult:
    companies_processed: int
    digest_date: date


async def _company_ids(session: AsyncSession) -> list[uuid.UUID]:
    result = await session.execute(text("SELECT id FROM companies"))
    return [row.id for row in result]


async def _summarize_company(
    session: AsyncSession, company_id: uuid.UUID, today: date
) -> dict[str, int]:
    start = datetime.combine(today, time.min, tzinfo=UTC)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=UTC)

    counts = await session.execute(
        text(
            "SELECT action, count(*) AS n FROM audit_logs "
            "WHERE company_id = :cid AND created_at >= :start AND created_at < :end "
            "GROUP BY action"
        ),
        {"cid": str(company_id), "start": start, "end": end},
    )
    action_counts = {row.action: row.n for row in counts}

    needs_review = await session.execute(
        text(
            "SELECT count(*) FROM records "
            "WHERE company_id = :cid AND needs_review = true AND is_deleted = false"
        ),
        {"cid": str(company_id)},
    )

    summary = {action.lower(): action_counts.get(action, 0) for action in _TRACKED_ACTIONS}
    summary["needs_review_count"] = needs_review.scalar_one()
    return summary


async def build_digests(session: AsyncSession, *, today: date | None = None) -> DigestResult:
    """The directly-testable core — takes a session rather than opening its
    own, the same split `audit_chain_verify.verify_chain`/`run` uses. Tests
    pass the superuser `session` fixture (already RLS-exempt, same
    effective access as `migrator`) instead of needing real
    `DATABASE_URL_MIGRATOR` credentials in the test environment."""
    today = today or datetime.now(tz=UTC).date()
    company_ids = await _company_ids(session)
    for company_id in company_ids:
        summary = await _summarize_company(session, company_id, today)
        await session.execute(
            text(
                "INSERT INTO daily_digests (company_id, digest_date, summary) "
                "VALUES (:cid, :date, CAST(:summary AS jsonb)) "
                "ON CONFLICT (company_id, digest_date) "
                "DO UPDATE SET summary = EXCLUDED.summary"
            ),
            {"cid": str(company_id), "date": today, "summary": json.dumps(summary)},
        )
    await session.commit()
    return DigestResult(companies_processed=len(company_ids), digest_date=today)


async def run() -> DigestResult:
    async with get_migrator_session() as session:
        return await build_digests(session)
