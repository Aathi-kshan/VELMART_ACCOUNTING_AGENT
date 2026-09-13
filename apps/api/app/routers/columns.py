"""Column endpoints (plan sections 10.2, 10.3, 21.2; docs/API.md §4). Owner
only, all of them."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.dependencies.db import get_rls_session
from app.dependencies.guards import require_owner
from app.schemas.column import (
    ColumnDefinition,
    ColumnOut,
    NarrowDryRunRequest,
    NarrowDryRunResult,
    UpdateColumnRequest,
    UpdateColumnResponse,
)
from app.services import schema_service

router = APIRouter(tags=["columns"])


@router.post("/pages/{page_id}/columns", response_model=ColumnOut, status_code=201)
async def add_column(
    page_id: uuid.UUID,
    payload: ColumnDefinition,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> ColumnOut:
    column = await schema_service.add_column(session, ctx, page_id, payload)
    return ColumnOut.model_validate(column)


@router.patch("/columns/{column_id}", response_model=UpdateColumnResponse)
async def update_column(
    column_id: uuid.UUID,
    payload: UpdateColumnRequest,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> UpdateColumnResponse:
    column, removed_options_in_use = await schema_service.update_column(
        session, ctx, column_id, payload
    )
    return UpdateColumnResponse(
        **ColumnOut.model_validate(column).model_dump(),
        removed_options_in_use=removed_options_in_use,
    )


@router.delete("/columns/{column_id}", response_model=ColumnOut)
async def archive_column(
    column_id: uuid.UUID,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> ColumnOut:
    column, _ = await schema_service.update_column(
        session, ctx, column_id, UpdateColumnRequest(is_archived=True)
    )
    return ColumnOut.model_validate(column)


@router.post("/columns/{column_id}/narrow-dry-run", response_model=NarrowDryRunResult)
async def narrow_dry_run(
    column_id: uuid.UUID,
    payload: NarrowDryRunRequest,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> NarrowDryRunResult:
    return await schema_service.narrow_dry_run(session, ctx, column_id, payload.data_type)
