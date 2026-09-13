"""CSV import (plan section 13.1, P3.5 Part 3) — owner only, one generic
pipeline for any page: `preview` -> `validate` -> `commit` -> optional
`rollback` within 24 hours.

Every step re-uploads the file; there is no server-side session for a
partially-completed import (see `csv_service.py`'s module docstring). The
Owner's confirmed mapping/dedup choice travels as one JSON-encoded form
field (`payload`) alongside the file, since a multipart request can't carry
a nested JSON body directly.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.context import SecurityContext
from app.core.errors import ValidationFailedError
from app.dependencies.db import get_rls_session
from app.dependencies.guards import require_owner
from app.schemas.csv_import import (
    ImportBatchOut,
    ImportCommitResponse,
    ImportMappingRequest,
    ImportPreviewResponse,
    ImportRollbackResponse,
    ImportValidateResponse,
)
from app.services import csv_service, page_service

router = APIRouter(tags=["imports"])


async def _read_file(file: UploadFile) -> bytes:
    settings = get_settings()
    raw = await file.read()
    max_bytes = settings.MAX_CSV_MB * 1024 * 1024
    if len(raw) > max_bytes:
        raise ValidationFailedError(f"File exceeds the {settings.MAX_CSV_MB} MB limit.")
    return raw


def _parse_payload(payload: str) -> ImportMappingRequest:
    try:
        return ImportMappingRequest.model_validate_json(payload)
    except ValueError as exc:
        raise ValidationFailedError(f"Invalid mapping payload: {exc}") from exc


@router.post("/pages/{page_id}/import/preview", response_model=ImportPreviewResponse)
async def preview_import(
    page_id: uuid.UUID,
    file: UploadFile,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> ImportPreviewResponse:
    page = await page_service.get_page_for_ctx(session, ctx, page_id, need="view")
    columns = await page_service.get_page_columns(session, page.id)
    raw = await _read_file(file)
    return await csv_service.preview_import(raw, page, columns)


@router.post("/pages/{page_id}/import/validate", response_model=ImportValidateResponse)
async def validate_import(
    page_id: uuid.UUID,
    file: UploadFile,
    payload: str = Form(...),
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> ImportValidateResponse:
    page = await page_service.get_page_for_ctx(session, ctx, page_id, need="view")
    columns = await page_service.get_page_columns(session, page.id)
    raw = await _read_file(file)
    parsed_payload = _parse_payload(payload)
    return await csv_service.validate_import(session, ctx, page, columns, raw, parsed_payload)


@router.post("/pages/{page_id}/import/commit", response_model=ImportCommitResponse)
async def commit_import(
    page_id: uuid.UUID,
    file: UploadFile,
    payload: str = Form(...),
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> ImportCommitResponse:
    page = await page_service.get_page_for_ctx(session, ctx, page_id, need="create")
    columns = await page_service.get_page_columns(session, page.id)
    raw = await _read_file(file)
    return await csv_service.commit_import(
        session, ctx, page, columns, raw, _parse_payload(payload), file.filename or "import.csv"
    )


@router.get("/pages/{page_id}/import-batches", response_model=list[ImportBatchOut])
async def list_import_batches(
    page_id: uuid.UUID,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> list[ImportBatchOut]:
    page = await page_service.get_page_for_ctx(session, ctx, page_id, need="view")
    return await csv_service.list_import_batches(session, ctx, page.id)


@router.post("/import-batches/{batch_id}/rollback", response_model=ImportRollbackResponse)
async def rollback_import(
    batch_id: uuid.UUID,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> ImportRollbackResponse:
    return await csv_service.rollback_import(session, ctx, batch_id)
