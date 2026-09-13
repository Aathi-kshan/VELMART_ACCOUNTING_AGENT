"""Query, aggregate, and column-value discovery (plan sections 3.8, 3.9,
21.2; docs/API.md §5). All three are the 🟡 filtered case — granted view.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.dependencies.auth import security_context
from app.dependencies.db import get_rls_session
from app.schemas.common import Paginated
from app.schemas.record import (
    AggregateRequest,
    AggregateResponse,
    ColumnValuesResponse,
    QueryRequest,
    RecordOut,
    RunningBalanceResponse,
)
from app.services import page_service, query_service

router = APIRouter(tags=["query"])


@router.post("/pages/{page_id}/records/query", response_model=Paginated[RecordOut])
async def query_records(
    page_id: uuid.UUID,
    payload: QueryRequest,
    ctx: SecurityContext = Depends(security_context),
    session: AsyncSession = Depends(get_rls_session),
) -> Paginated[RecordOut]:
    page = await page_service.get_page_for_ctx(session, ctx, page_id, need="view")
    columns = await page_service.get_page_columns(session, page.id)
    return await query_service.query_records(session, page, columns, payload)


@router.post("/pages/{page_id}/aggregate", response_model=AggregateResponse)
async def aggregate(
    page_id: uuid.UUID,
    payload: AggregateRequest,
    ctx: SecurityContext = Depends(security_context),
    session: AsyncSession = Depends(get_rls_session),
) -> AggregateResponse:
    page = await page_service.get_page_for_ctx(session, ctx, page_id, need="view")
    columns = await page_service.get_page_columns(session, page.id)
    return await query_service.aggregate(session, page, columns, payload)


@router.get("/pages/{page_id}/running-balance", response_model=RunningBalanceResponse)
async def running_balance(
    page_id: uuid.UUID,
    ctx: SecurityContext = Depends(security_context),
    session: AsyncSession = Depends(get_rls_session),
) -> RunningBalanceResponse:
    page = await page_service.get_page_for_ctx(session, ctx, page_id, need="view")
    columns = await page_service.get_page_columns(session, page.id)
    entries = await query_service.running_balance(session, page, columns)
    return RunningBalanceResponse(entries=entries)


@router.get("/pages/{page_id}/column-values/{key}", response_model=ColumnValuesResponse)
async def column_values(
    page_id: uuid.UUID,
    key: str,
    ctx: SecurityContext = Depends(security_context),
    session: AsyncSession = Depends(get_rls_session),
) -> ColumnValuesResponse:
    page = await page_service.get_page_for_ctx(session, ctx, page_id, need="view")
    columns = await page_service.get_page_columns(session, page.id)
    values = await query_service.column_values(session, page, columns, key)
    return ColumnValuesResponse(values=values)
