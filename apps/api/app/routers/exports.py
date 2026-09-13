"""`POST /pages/{page_id}/export` (plan section 13.2 / P3.5 Part 2).
Owner only, same as import. See `app/services/csv_service.py`'s module
docstring for how this deviates from the locked spec's presigned-URL
delivery mechanism.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.dependencies.db import get_rls_session
from app.dependencies.guards import require_owner
from app.schemas.record import ExportRequest
from app.services import csv_service, page_service
from app.services.audit_service import write_audit_log

router = APIRouter(tags=["exports"])


@router.post("/pages/{page_id}/export")
async def export_page(
    page_id: uuid.UUID,
    payload: ExportRequest,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> Response:
    page = await page_service.get_page_for_ctx(session, ctx, page_id, need="view")
    columns = await page_service.get_page_columns(session, page.id)

    csv_bytes, row_count = await csv_service.export_records_csv(session, page, columns, payload)

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="CSV_EXPORT",
        entity_type="page",
        entity_id=page.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        new_data={
            "row_count": row_count,
            "filters": [f.model_dump(mode="json") for f in payload.filters],
        },
    )

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{page.key}.csv"'},
    )
