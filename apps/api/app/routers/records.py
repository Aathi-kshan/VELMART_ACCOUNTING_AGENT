"""Record endpoints (plan sections 3.6, 3.7, 21.2; docs/API.md §5). The same
code path serves every page — Owner-created or system.

`POST /pages/{id}/records` is the 🟡 filtered create case: granted view
alone isn't enough, `page_service.get_page_for_ctx(need="create")` checks
the stronger permission. `PATCH`/`DELETE /records/{id}` are owner-only.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.errors import ConflictError, ValidationFailedError
from app.core.idempotency import (
    IdempotencyConflictError,
    hash_request,
    lookup,
    reserve,
    store_response,
)
from app.dependencies.auth import security_context
from app.dependencies.db import get_rls_session
from app.dependencies.guards import require_owner
from app.schemas.common import Paginated
from app.schemas.record import (
    CreateRecordRequest,
    DeleteRecordRequest,
    QueryRequest,
    RecordOut,
    ReverseRecordRequest,
    ReverseRecordResponse,
    SetProtectedFieldRequest,
    UpdateRecordRequest,
)
from app.services import page_service, protected_field_service, query_service, record_service

router = APIRouter(tags=["records"])

_CREATE_ENDPOINT = "POST /pages/{id}/records"


@router.post("/pages/{page_id}/records", response_model=RecordOut, status_code=201)
async def create_record(
    page_id: uuid.UUID,
    payload: CreateRecordRequest,
    request: Request,
    ctx: SecurityContext = Depends(security_context),
    session: AsyncSession = Depends(get_rls_session),
) -> RecordOut:
    page = await page_service.get_page_for_ctx(session, ctx, page_id, need="create")
    columns = await page_service.get_page_columns(session, page.id)

    idem_key = request.headers.get("Idempotency-Key")
    if idem_key:
        request_hash = hash_request(payload.model_dump(mode="json"))
        try:
            stored = await lookup(
                session,
                company_id=ctx.company_id,
                key=idem_key,
                endpoint=_CREATE_ENDPOINT,
                request_hash=request_hash,
            )
        except IdempotencyConflictError as exc:
            raise ConflictError(str(exc)) from exc
        if stored is not None:
            return RecordOut.model_validate(stored.body)
        won = await reserve(
            session,
            company_id=ctx.company_id,
            key=idem_key,
            user_id=ctx.user_id,
            endpoint=_CREATE_ENDPOINT,
            request_hash=request_hash,
        )
        if not won:
            raise ConflictError("A request with this Idempotency-Key is already being processed.")

    record = await record_service.create_record(session, ctx, page, columns, payload)
    out = RecordOut.model_validate(record)

    if idem_key:
        await store_response(
            session,
            company_id=ctx.company_id,
            key=idem_key,
            status_code=201,
            body=out.model_dump(mode="json"),
        )
    return out


@router.get("/pages/{page_id}/records", response_model=Paginated[RecordOut])
async def list_records(
    page_id: uuid.UUID,
    cursor: str | None = None,
    limit: int = 50,
    ctx: SecurityContext = Depends(security_context),
    session: AsyncSession = Depends(get_rls_session),
) -> Paginated[RecordOut]:
    page = await page_service.get_page_for_ctx(session, ctx, page_id, need="view")
    columns = await page_service.get_page_columns(session, page.id)
    return await query_service.query_records(
        session, page, columns, QueryRequest(cursor=cursor, limit=limit)
    )


@router.get("/records/{record_id}", response_model=RecordOut)
async def get_record(
    record_id: uuid.UUID,
    ctx: SecurityContext = Depends(security_context),
    session: AsyncSession = Depends(get_rls_session),
) -> RecordOut:
    record = await record_service.get_record(session, ctx, record_id)
    return RecordOut.model_validate(record)


@router.patch("/records/{record_id}", response_model=RecordOut)
async def update_record(
    record_id: uuid.UUID,
    payload: UpdateRecordRequest,
    request: Request,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> RecordOut:
    version = payload.version
    if_match = request.headers.get("If-Match")
    if if_match is not None:
        try:
            version = int(if_match)
        except ValueError as exc:
            raise ValidationFailedError("If-Match must be an integer version.") from exc

    record = await record_service.update_record(session, ctx, record_id, payload, version)
    return RecordOut.model_validate(record)


@router.delete("/records/{record_id}", status_code=204)
async def delete_record(
    record_id: uuid.UUID,
    payload: DeleteRecordRequest,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> None:
    await record_service.delete_record(session, ctx, record_id, payload.reason)


@router.patch("/records/{record_id}/protected-field", response_model=RecordOut)
async def set_protected_field(
    record_id: uuid.UUID,
    payload: SetProtectedFieldRequest,
    request: Request,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> RecordOut:
    """The only way a protected column (e.g. `cheques.cheque_status`)
    changes after create (plan section 11.4) — owner-only."""
    version = payload.version
    if_match = request.headers.get("If-Match")
    if if_match is not None:
        try:
            version = int(if_match)
        except ValueError as exc:
            raise ValidationFailedError("If-Match must be an integer version.") from exc

    handle = await protected_field_service.set_protected_field(
        session, ctx, record_id, payload.column_key, payload.value, version
    )
    return RecordOut.model_validate(handle)


@router.post("/records/{record_id}/reverse", response_model=ReverseRecordResponse)
async def reverse_record(
    record_id: uuid.UUID,
    payload: ReverseRecordRequest,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> ReverseRecordResponse:
    """`kind=LEDGER` pages only (plan section 11.5, P4 §8) — the only way
    such a page's record is corrected after create."""
    original, replacement = await record_service.reverse_record(session, ctx, record_id, payload)
    return ReverseRecordResponse(
        original=RecordOut.model_validate(original),
        replacement=RecordOut.model_validate(replacement) if replacement else None,
    )
