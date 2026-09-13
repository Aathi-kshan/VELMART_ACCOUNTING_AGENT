"""Audit log endpoints (plan section 18.3, P5). `GET /audit-logs` is the 🟡
filtered case — a manager sees a real, view-gated subset, never a 403
(same shape as `GET /pages`); `GET /audit-logs/export` is Owner-only.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.dependencies.auth import security_context
from app.dependencies.db import get_rls_session
from app.dependencies.guards import require_owner
from app.schemas.audit import AuditLogPage, AuditLogQuery
from app.services import audit_read_service

router = APIRouter(tags=["audit"])


@router.get("/audit-logs", response_model=AuditLogPage)
async def list_audit_logs(
    actor_user_id: uuid.UUID | None = None,
    page_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    source: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    ctx: SecurityContext = Depends(security_context),
    session: AsyncSession = Depends(get_rls_session),
) -> AuditLogPage:
    query = AuditLogQuery(
        actor_user_id=actor_user_id,
        page_id=page_id,
        entity_type=entity_type,
        date_from=date_from,
        date_to=date_to,
        source=source,
        cursor=cursor,
        limit=limit,
    )
    return await audit_read_service.query_audit_logs(session, ctx, query)


@router.get("/audit-logs/export")
async def export_audit_logs(
    actor_user_id: uuid.UUID | None = None,
    page_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    source: str | None = None,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> Response:
    query = AuditLogQuery(
        actor_user_id=actor_user_id,
        page_id=page_id,
        entity_type=entity_type,
        date_from=date_from,
        date_to=date_to,
        source=source,
        limit=500,
    )
    csv_bytes = await audit_read_service.export_audit_logs_csv(session, ctx, query)
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'},
    )
