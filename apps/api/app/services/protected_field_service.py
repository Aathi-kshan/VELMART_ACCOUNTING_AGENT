"""The dedicated path for changing a protected column's value (plan section
11.4) — owner-only (enforced by the router's `require_owner`, same as
`record_service.update_record`), the only way `cheques.cheque_status` (or
any other page's `is_protected` SELECT column) ever changes after create.
`record_service`'s generic create/update path rejects any attempt to touch
one of these, by design (see its module docstring) — this is where that
rejection points the caller instead.
"""

from __future__ import annotations

import uuid

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.errors import NotFoundError, ValidationFailedError, VersionConflictError
from app.models.page_column import ColumnType
from app.repositories.records import (
    RecordHandle,
    find_record,
    generated_columns_for,
    get_row,
    update_row,
)
from app.schemas.dynamic import build_record_model
from app.services import page_service
from app.services.audit_service import write_audit_log


async def set_protected_field(
    session: AsyncSession,
    ctx: SecurityContext,
    record_id: uuid.UUID,
    column_key: str,
    value: str,
    version: int | None,
    *,
    source: str = "APP",
    ai_session_id: uuid.UUID | None = None,
) -> RecordHandle:
    """`source`/`ai_session_id` (P8): every existing caller is the human-
    facing `PATCH /records/{id}/protected-field` route and gets the
    untouched defaults; the proposal-apply endpoint is the only caller that
    ever passes `source="AI"`."""
    system_pages = await page_service.list_system_pages(session, ctx.company_id)
    page = await find_record(session, ctx.company_id, record_id, system_pages)
    if page is None:
        raise NotFoundError("No such record.")
    columns = await page_service.get_page_columns(session, page.id)
    handle = await get_row(session, page, columns, record_id, ctx.company_id)
    if handle is None or handle.is_deleted:
        raise NotFoundError("No such record.")

    columns_by_key = {c.key: c for c in columns}
    column = columns_by_key.get(column_key)
    if column is None or not column.is_protected or column.data_type is not ColumnType.SELECT:
        raise ValidationFailedError(f"{column_key!r} is not a protected field on this page.")

    options = column.config.get("options") or []
    if value not in options:
        raise ValidationFailedError(f"{column.name}: must be one of {options}.")

    if version is None:
        raise ValidationFailedError("A version (If-Match header or body 'version') is required.")
    if version != handle.version:
        raise VersionConflictError(
            f"This record has changed since version {version}.",
            extra={"current_version": handle.version},
        )

    readonly_extra = generated_columns_for(page)
    full_data = {k: v for k, v in handle.data.items() if k not in readonly_extra}
    full_data[column_key] = value
    model = build_record_model(columns, readonly_extra=readonly_extra)
    try:
        validated = model(**full_data).model_dump()
    except ValidationError as exc:
        raise ValidationFailedError(
            "The record data did not match this page's schema.",
            extra={"errors": exc.errors(include_url=False, include_context=False)},
        ) from exc

    old_value = handle.data.get(column_key)
    updated = await update_row(
        session,
        page,
        handle,
        columns,
        validated=validated,
        occurred_at=handle.occurred_at,
        store_id=None,
        business_date=handle.business_date,
        updated_by=ctx.user_id,
    )

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="PROTECTED_FIELD_CHANGE",
        entity_type="record",
        entity_id=updated.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        old_data={"column": column_key, "value": old_value},
        new_data={"column": column_key, "value": value},
        source=source,
        ai_session_id=ai_session_id,
    )
    return updated
