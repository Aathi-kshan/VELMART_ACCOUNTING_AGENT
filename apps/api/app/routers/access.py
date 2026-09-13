"""Page access grants (plan sections 3.10, 4.3, 21.2; docs/API.md §4). Owner
only — default-deny, wholesale replace."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.dependencies.db import get_rls_session
from app.dependencies.guards import require_owner
from app.schemas.page import AccessGrant, PutPageAccessRequest
from app.services import page_service

router = APIRouter(tags=["access"])


@router.put("/pages/{page_id}/access", response_model=list[AccessGrant])
async def set_page_access(
    page_id: uuid.UUID,
    payload: PutPageAccessRequest,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> list[AccessGrant]:
    grants = [g.model_dump() for g in payload.grants]
    rows = await page_service.set_page_access(session, ctx, page_id, grants)
    return [AccessGrant.model_validate(r) for r in rows]
