"""`GET /reconciliation` (plan section 3.5.11, docs/API.md §1.8) — the one
workflow only the six system pages enable, comparing `daily_revenue` against
`cash_ledger` for the same business date — and configurable dashboard
widgets (plan section 15, P5).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.errors import NotFoundError
from app.dependencies.auth import security_context
from app.dependencies.db import get_rls_session
from app.dependencies.guards import require_page_access
from app.schemas.dashboard import (
    DailyDigestOut,
    ReconciliationResponse,
)
from app.services import dashboard_service, page_service

router = APIRouter(tags=["dashboard"])

_REQUIRED_PAGE_KEYS = ("daily_revenue", "cash_ledger")


@router.get("/reconciliation", response_model=ReconciliationResponse)
async def get_reconciliation(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    ctx: SecurityContext = Depends(security_context),
    session: AsyncSession = Depends(get_rls_session),
) -> ReconciliationResponse:
    for key in _REQUIRED_PAGE_KEYS:
        page = await page_service.get_page_by_key(session, ctx.company_id, key)
        if page is None:
            raise NotFoundError(
                "Reconciliation requires the daily_revenue and cash_ledger system pages."
            )
        if not ctx.is_owner:
            await require_page_access(page.id, "view", ctx, session)

    items = await dashboard_service.get_reconciliation(session, ctx, from_, to)
    return ReconciliationResponse(items=items)


@router.get("/dashboard/digest", response_model=DailyDigestOut | None)
async def get_digest(
    for_date: date | None = Query(default=None, alias="date"),
    ctx: SecurityContext = Depends(security_context),
    session: AsyncSession = Depends(get_rls_session),
) -> DailyDigestOut | None:
    return await dashboard_service.get_digest(session, ctx, for_date)
