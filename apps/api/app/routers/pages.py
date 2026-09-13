"""Page endpoints (plan sections 10.1, 21.2; docs/API.md §4).

Create/edit/archive are owner-only; list/schema are the 🟡 filtered case —
`page_service.list_pages`/`get_page_schema` do the filtering, not a guard
dependency here (see app/dependencies/guards.py's module docstring for why).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.errors import NotFoundError
from app.dependencies.auth import security_context
from app.dependencies.db import get_rls_session
from app.dependencies.guards import require_owner
from app.models.page import Page
from app.repositories.records import generated_columns_for
from app.schemas.column import ColumnOut
from app.schemas.page import CreatePageRequest, PageOut, PageSchemaOut, UpdatePageRequest
from app.services import page_service

router = APIRouter(tags=["pages"])


async def _schema_out(session: AsyncSession, page: Page) -> PageSchemaOut:
    columns = await page_service.get_page_columns(session, page.id)
    return PageSchemaOut(
        **PageOut.model_validate(page).model_dump(),
        columns=[ColumnOut.model_validate(c) for c in columns],
        generated_columns=sorted(generated_columns_for(page)),
    )


@router.post("/pages", response_model=PageSchemaOut, status_code=201)
async def create_page(
    payload: CreatePageRequest,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> PageSchemaOut:
    page = await page_service.create_page(session, ctx, payload)
    return await _schema_out(session, page)


@router.get("/pages", response_model=list[PageOut])
async def list_pages(
    ctx: SecurityContext = Depends(security_context),
    session: AsyncSession = Depends(get_rls_session),
) -> list[PageOut]:
    pages = await page_service.list_pages(session, ctx)
    return [PageOut.model_validate(p) for p in pages]


@router.get("/pages/{page_id}/schema", response_model=PageSchemaOut)
async def get_page_schema(
    page_id: uuid.UUID,
    ctx: SecurityContext = Depends(security_context),
    session: AsyncSession = Depends(get_rls_session),
) -> PageSchemaOut:
    page, _columns = await page_service.get_page_schema(session, ctx, page_id)
    return await _schema_out(session, page)


@router.patch("/pages/{page_id}", response_model=PageSchemaOut)
async def update_page(
    page_id: uuid.UUID,
    payload: UpdatePageRequest,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> PageSchemaOut:
    page = await page_service.update_page(session, ctx, page_id, payload)
    if page is None:
        raise NotFoundError("No such page.")
    return await _schema_out(session, page)


@router.delete("/pages/{page_id}", response_model=PageOut)
async def archive_page(
    page_id: uuid.UUID,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> PageOut:
    page = await page_service.archive_page(session, ctx, page_id)
    if page is None:
        raise NotFoundError("No such page.")
    return PageOut.model_validate(page)
