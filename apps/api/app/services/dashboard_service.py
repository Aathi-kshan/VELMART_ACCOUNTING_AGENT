"""Daily reconciliation (plan section 3.5.11 / 12.5, docs/API.md §1.8) and
configurable dashboard widgets (plan section 15, P5).

Reconciliation reads straight from the `daily_reconciliation` view
(migration 0008) — a `SECURITY INVOKER` view, so Postgres's own
`store_scope` RLS policy on `daily_revenue`/`cash_ledger` already restricts
what a manager's totals sum to, exactly as it would querying either table
directly. No application-level store filtering happens here; `WHERE
company_id = ...` below is defense in depth (the same table's own
`tenant_isolation` policy already guarantees it), not the thing doing the
real scoping.

Access control (both `daily_revenue` and `cash_ledger` system pages must be
`view`-granted, 404 for either missing) is the router's job — this function
assumes that's already been checked and just reads.

Widget evaluation reuses `query_service.py`'s `aggregate`/`query_records`
directly for four of the five widget types — a widget's `config` embeds the
same `AggregateRequest`/`QueryRequest` shapes, not a second query language.
`TREND` is the one exception: neither existing function has day/week
bucketing, so it gets one small, contained query here rather than growing
the shared query engine for a dashboard-only need.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.money import format_money
from app.models.daily_digest import DailyDigest
from app.schemas.dashboard import (
    DailyDigestOut,
    ReconciliationItem,
)


async def get_reconciliation(
    session: AsyncSession,
    ctx: SecurityContext,
    date_from: date | None,
    date_to: date | None,
) -> list[ReconciliationItem]:
    conditions = ["company_id = :company_id"]
    params: dict[str, object] = {"company_id": str(ctx.company_id)}
    if date_from is not None:
        conditions.append("business_date >= :date_from")
        params["date_from"] = date_from
    if date_to is not None:
        conditions.append("business_date <= :date_to")
        params["date_to"] = date_to

    # noqa justification: `sql` is built entirely from the two hardcoded
    # strings above, never from caller input — only their associated
    # *values* (bound as `params`) come from the request, and those go
    # through SQLAlchemy bind parameters, not string interpolation.
    sql = (
        "SELECT business_date, revenue_total, ledger_total, difference "  # noqa: S608
        f"FROM daily_reconciliation WHERE {' AND '.join(conditions)} "
        "ORDER BY business_date"
    )
    query = text(sql)
    result = await session.execute(query, params)
    return [
        ReconciliationItem(
            business_date=row.business_date,
            revenue_total=format_money(row.revenue_total),
            ledger_total=format_money(row.ledger_total),
            difference=format_money(row.difference),
        )
        for row in result
    ]


# --------------------------------------------------------------------------
# Widgets (plan section 15, P5)
# --------------------------------------------------------------------------

async def get_digest(
    session: AsyncSession, ctx: SecurityContext, digest_date: date | None
) -> DailyDigestOut | None:
    """Already company-scoped by RLS (`daily_digests`' own `tenant_isolation`
    policy, migration 0013) — no extra gate needed, unlike widgets/audit
    which have their own role/page-visibility rules on top of tenancy."""
    target_date = digest_date or date.today()
    result = await session.execute(
        select(DailyDigest).where(
            DailyDigest.company_id == ctx.company_id, DailyDigest.digest_date == target_date
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return DailyDigestOut(digest_date=row.digest_date, summary=row.summary)
