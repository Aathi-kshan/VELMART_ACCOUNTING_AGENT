"""`page_validations` endpoints (plan section 11.3, P4 §6; docs/API.md §4).
Owner only, all of them — matching the column-management convention.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.errors import NotFoundError
from app.dependencies.db import get_rls_session
from app.dependencies.guards import require_owner
from app.models.page import Page
from app.repositories.base import get_for_company
from app.schemas.validation import ValidationRuleCreate, ValidationRuleOut, ValidationRuleUpdate
from app.services import page_service, validation_service

router = APIRouter(tags=["validations"])


@router.post("/pages/{page_id}/validations", response_model=ValidationRuleOut, status_code=201)
async def create_validation(
    page_id: uuid.UUID,
    payload: ValidationRuleCreate,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> ValidationRuleOut:
    page = await get_for_company(session, Page, page_id, ctx.company_id)
    if page is None:
        raise NotFoundError("No such page.")
    columns = await page_service.get_page_columns(session, page.id)
    rule = await validation_service.create_rule(session, ctx, page, columns, payload)
    return ValidationRuleOut.model_validate(rule)


@router.patch("/validations/{rule_id}", response_model=ValidationRuleOut)
async def update_validation(
    rule_id: uuid.UUID,
    payload: ValidationRuleUpdate,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> ValidationRuleOut:
    rule = await validation_service.update_rule(session, ctx, rule_id, payload)
    return ValidationRuleOut.model_validate(rule)


@router.delete("/validations/{rule_id}", response_model=ValidationRuleOut)
async def archive_validation(
    rule_id: uuid.UUID,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> ValidationRuleOut:
    rule = await validation_service.archive_rule(session, ctx, rule_id)
    return ValidationRuleOut.model_validate(rule)
