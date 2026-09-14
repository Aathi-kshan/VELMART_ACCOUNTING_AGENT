"""Record CRUD (plan sections 3.6, 3.7, 9.1, 9.2, 10.4, 11.4). The same code
path serves every page — Owner-created *or* system (Employee Salary,
Purchases, Expenses, Daily Revenue, Cash Ledger, Cheques) — by going through
`app/repositories/records.py`'s storage dispatch rather than the `Record`
model directly.

What's enforced here: per-column type/required/range/options validation
(the dynamic model, `app/schemas/dynamic.py`), `STORE_REF`/`USER_REF`/
`RECORD_REF` existence (the first two against platform tables directly;
`RECORD_REF` via `app/services/reference_service.py`, P4 §5, which also
blocks deleting a record anything still references), protected-field
enforcement (plan section 11.4): a protected column is never set (by a
non-owner) or changed (by anyone) through this generic path, only through
the dedicated `protected_field_service.py`; and `kind=LEDGER` immutability
— such a page's records are corrected by `reverse_record` (P4 §8), never
edited in place.

`page_validations` (Owner-configured ERROR/WARNING rules) was a separate
feature layered on top of this and has been removed entirely (product
decision) — `needs_review` is still a real platform field (consumed by the
review-queue filter and the `REVIEW_QUEUE` dashboard widget type), it just
has no remaining code path that ever sets it back to `True`.

Like the other P3 services, nothing here commits — callers use
`get_rls_session`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.dates import DEFAULT_DAY_CUTOFF_HOUR, business_date_for
from app.core.errors import (
    LedgerRecordImmutableError,
    NotFoundError,
    ProtectedFieldForbiddenError,
    ValidationFailedError,
    VersionConflictError,
)
from app.db.base import RecordStatus
from app.dependencies.guards import require_page_access
from app.models.company import CompanySettings
from app.models.page import Page, PageKind
from app.models.page_column import ColumnType, PageColumn
from app.models.record import Record
from app.models.store import Store
from app.models.user import User
from app.repositories.records import (
    RecordHandle,
    create_row,
    find_record,
    generated_columns_for,
    get_row,
    soft_delete_row,
    update_row,
)
from app.schemas.dynamic import build_record_model
from app.schemas.record import CreateRecordRequest, ReverseRecordRequest, UpdateRecordRequest
from app.services import formula_service, page_service, reference_service
from app.services.audit_service import write_audit_log

_REF_TYPES = {ColumnType.STORE_REF: Store, ColumnType.USER_REF: User}


async def validate_references(
    session: AsyncSession,
    ctx: SecurityContext,
    columns: list[PageColumn],
    validated: dict[str, Any],
) -> None:
    """`STORE_REF`/`USER_REF` point at platform tables that already exist, so
    they're checked directly here; `RECORD_REF` points at another *page's*
    row, so its existence check (and the delete-blocking it implies) lives
    in `app/services/reference_service.py` instead.

    Public (not `_`-prefixed): `app/ai/tools/propose_tools.py` (P8) reuses
    this exact check when validating a proposed change, rather than
    re-implementing reference validation a second time."""
    for column in columns:
        model = _REF_TYPES.get(column.data_type)
        if model is None:
            continue
        value = validated.get(column.key)
        if value is None:
            continue
        found = await session.execute(
            select(model.id).where(model.id == value, model.company_id == ctx.company_id)  # type: ignore[attr-defined]
        )
        if found.scalar_one_or_none() is None:
            kind = "store" if column.data_type is ColumnType.STORE_REF else "user"
            raise ValidationFailedError(f"{column.name}: no such {kind}.")
    await reference_service.validate_record_refs(session, ctx, columns, validated)


def _protected_keys(columns: list[PageColumn]) -> set[str]:
    return {c.key for c in columns if c.is_protected}


def _check_protected_on_create(
    ctx: SecurityContext, columns: list[PageColumn], raw_data: dict[str, Any]
) -> None:
    """A manager supplying *any* value for a protected column — even the
    correct default — is rejected outright; an owner's create is
    unaffected (plan section 11.4)."""
    if ctx.is_owner:
        return
    supplied = _protected_keys(columns) & raw_data.keys()
    if supplied:
        raise ProtectedFieldForbiddenError(
            "Only owners can set a protected field.", extra={"fields": sorted(supplied)}
        )


def _check_protected_on_update(
    columns: list[PageColumn], current_data: dict[str, Any], raw_changes: dict[str, Any]
) -> None:
    """No one — owner included — changes a protected column's *value* through
    the generic update path; only the dedicated
    `PATCH /records/{id}/protected-field` endpoint does.

    Checked against the record's *current* value, not mere key presence
    (a P4 bug fix): a client that round-trips a record's full data on every
    edit — as `record_form_screen.dart` does — always resubmits a protected
    column's unchanged value alongside whatever it actually meant to
    change. Rejecting on presence alone made editing *any* other field on a
    record with a protected column 403 unconditionally; only a genuine
    attempted change should be rejected here."""
    protected = _protected_keys(columns)
    changed = {
        key
        for key in (protected & raw_changes.keys())
        if raw_changes[key] != current_data.get(key)
    }
    if changed:
        raise ProtectedFieldForbiddenError(
            "Protected fields change only through "
            "PATCH /records/{id}/protected-field.",
            extra={"fields": sorted(changed)},
        )


async def _derive_business_date(
    session: AsyncSession,
    ctx: SecurityContext,
    page: Page,
    occurred_at: datetime,
    validated: dict[str, Any],
) -> date:
    """plan section 9.2: the page's own designated date column wins if set;
    otherwise `occurred_at` plus the company's cutoff hour."""
    if page.date_column_key:
        value = validated.get(page.date_column_key)
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value

    settings = await session.get(CompanySettings, ctx.company_id)
    cutoff = settings.day_cutoff_hour if settings else DEFAULT_DAY_CUTOFF_HOUR
    return business_date_for(occurred_at, cutoff_hour=cutoff)


def _derive_store_id(
    page: Page, validated: dict[str, Any], explicit_store_id: uuid.UUID | None
) -> uuid.UUID | None:
    if page.store_column_key:
        value = validated.get(page.store_column_key)
        if value is not None:
            return uuid.UUID(str(value))
    return explicit_store_id


def validate_payload(
    columns: list[PageColumn], data: dict[str, Any], *, readonly_extra: frozenset[str] = frozenset()
) -> dict[str, Any]:
    """Public (not `_`-prefixed): reused by `app/ai/tools/propose_tools.py`
    (P8) to validate a proposal's merged `after_data` the same way a real
    update validates its merged data — one schema-validation implementation,
    not two."""
    model = build_record_model(columns, readonly_extra=readonly_extra)
    try:
        return model(**data).model_dump()
    except ValidationError as exc:
        raise ValidationFailedError(
            "The record data did not match this page's schema.",
            extra={"errors": exc.errors(include_url=False, include_context=False)},
        ) from exc


async def create_record(
    session: AsyncSession,
    ctx: SecurityContext,
    page: Page,
    columns: list[PageColumn],
    payload: CreateRecordRequest,
) -> RecordHandle:
    _check_protected_on_create(ctx, columns, payload.data)

    readonly_extra = generated_columns_for(page)
    validated = validate_payload(columns, payload.data, readonly_extra=readonly_extra)
    await validate_references(session, ctx, columns, validated)

    business_date = await _derive_business_date(session, ctx, page, payload.occurred_at, validated)
    store_id = _derive_store_id(page, validated, payload.store_id)

    handle = await create_row(
        session,
        page,
        columns,
        company_id=ctx.company_id,
        store_id=store_id,
        occurred_at=payload.occurred_at,
        business_date=business_date,
        validated=validated,
        created_by=ctx.user_id,
        client_uuid=payload.client_uuid,
    )

    new_data = dict(handle.data)
    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="RECORD_CREATE",
        entity_type="record",
        entity_id=handle.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        new_data=new_data,
    )
    # Computed for the *response* only, never stored, and audited from the
    # real stored data above — never from a computed value (plan 11.1, P4 §4).
    handle.data = formula_service.apply_formulas(columns, handle.data)
    return handle


async def _locate(
    session: AsyncSession, ctx: SecurityContext, record_id: uuid.UUID
) -> tuple[Page, list[PageColumn], RecordHandle]:
    system_pages = await page_service.list_system_pages(session, ctx.company_id)
    page = await find_record(session, ctx.company_id, record_id, system_pages)
    if page is None:
        raise NotFoundError("No such record.")
    columns = await page_service.get_page_columns(session, page.id)
    handle = await get_row(session, page, columns, record_id, ctx.company_id)
    if handle is None or handle.is_deleted:
        raise NotFoundError("No such record.")
    return page, columns, handle


async def get_record(
    session: AsyncSession, ctx: SecurityContext, record_id: uuid.UUID
) -> RecordHandle:
    page, columns, handle = await _locate(session, ctx, record_id)
    if not ctx.is_owner:
        await require_page_access(page.id, "view", ctx, session)
    handle.data = formula_service.apply_formulas(columns, handle.data)
    return handle


def _check_version(handle: RecordHandle, version: int | None) -> None:
    if version is None:
        raise ValidationFailedError("A version (If-Match header or body 'version') is required.")
    if version != handle.version:
        raise VersionConflictError(
            f"This record has changed since version {version}.",
            extra={"current_version": handle.version},
        )


async def update_record(
    session: AsyncSession,
    ctx: SecurityContext,
    record_id: uuid.UUID,
    payload: UpdateRecordRequest,
    version: int | None,
    *,
    source: str = "APP",
    ai_session_id: uuid.UUID | None = None,
) -> RecordHandle:
    """Owner-only (enforced by the router's `require_owner`); every edit is
    audited with old and new values (docs/API.md §5).

    Unlike `create_record`, the caller can't know `page_id` (and so its
    columns) until the record itself is fetched — a path param only carries
    `record_id` — so this looks both up internally rather than taking them
    as parameters.

    `source`/`ai_session_id` (P8): every existing caller is the human-facing
    `PATCH /records/{id}` route and gets the untouched defaults. The
    proposal-apply endpoint (`app/ai/proposals.py`) is the only caller that
    ever passes `source="AI"`, so an applied proposal's audit entry
    correctly attributes the change to the AI session that proposed it."""
    page, columns, handle = await _locate(session, ctx, record_id)
    if page.kind is PageKind.LEDGER:
        raise LedgerRecordImmutableError(
            "A ledger-style page's records are corrected by reversal, never edited in place. "
            "Use POST /records/{id}/reverse instead."
        )
    _check_version(handle, version)
    _check_protected_on_update(columns, handle.data, payload.data)

    model = build_record_model(columns, partial=True, readonly_extra=generated_columns_for(page))
    try:
        changes = model(**payload.data).model_dump(exclude_unset=True)
    except ValidationError as exc:
        raise ValidationFailedError(
            "The record data did not match this page's schema.",
            extra={"errors": exc.errors(include_url=False, include_context=False)},
        ) from exc

    if changes:
        await validate_references(session, ctx, columns, changes)

    generated = generated_columns_for(page)
    old_data = dict(handle.data)
    merged = dict(handle.data)
    merged.update(changes)
    # A generated column's own current value (e.g. cash_ledger.total_amount)
    # is always present in the stored `handle.data` being merged from, but
    # `build_record_model` excludes generated keys as fields entirely (not
    # just read-only) — so re-validating the merged dict as-is would reject
    # every edit to a page with a generated column on its own untouched,
    # carried-over value. It's server-computed and never real input, so it's
    # dropped here the same way `create_row` never sends it to the DB.
    for key in generated:
        merged.pop(key, None)

    full_validated = validate_payload(columns, merged, readonly_extra=generated)
    business_date = await _derive_business_date(
        session, ctx, page, payload.occurred_at or handle.occurred_at, full_validated
    )

    updated = await update_row(
        session,
        page,
        handle,
        columns,
        validated=full_validated,
        occurred_at=payload.occurred_at or handle.occurred_at,
        store_id=payload.store_id,
        business_date=business_date,
        updated_by=ctx.user_id,
    )

    new_data = dict(updated.data)
    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="RECORD_UPDATE",
        entity_type="record",
        entity_id=updated.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        old_data=old_data,
        new_data=new_data,
        source=source,
        ai_session_id=ai_session_id,
    )
    updated.data = formula_service.apply_formulas(columns, updated.data)
    return updated


async def delete_record(
    session: AsyncSession, ctx: SecurityContext, record_id: uuid.UUID, reason: str
) -> RecordHandle:
    """Soft delete (owner-only, `reason` required). Blocked while any other
    page's `RECORD_REF` column still points at this record (P4 §5) — never
    silently orphaning a reference."""
    page, _columns, handle = await _locate(session, ctx, record_id)
    await reference_service.check_no_inbound_references(session, ctx, page, record_id)

    await soft_delete_row(session, page, handle, reason=reason, updated_by=ctx.user_id)

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="RECORD_DELETE",
        entity_type="record",
        entity_id=handle.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        old_data={"reason": reason},
    )
    return handle


async def reverse_record(
    session: AsyncSession, ctx: SecurityContext, record_id: uuid.UUID, payload: ReverseRecordRequest
) -> tuple[RecordHandle, RecordHandle | None]:
    """`kind=LEDGER` pages only (docs/PROJECT_PLAN.md §4.4's state machine):
    flips the original record `ACTIVE -> REVERSED` and, if `payload.data` is
    given, creates a new `ACTIVE` record linked via `reverses_id` — through
    `create_record`'s own pipeline (validation, references, formulas), not a
    parallel one. Scoped to Owner-created generic
    pages: `BusinessTableMixin` has no `reverses_id`-equivalent column, so a
    system page can't participate — unreachable in practice since every
    system page registers as `kind=REGISTER`, but checked explicitly rather
    than relying on that never changing silently."""
    page, columns, handle = await _locate(session, ctx, record_id)
    if page.kind is not PageKind.LEDGER:
        raise ValidationFailedError("Only a kind=LEDGER page's records can be reversed.")
    if page.storage_table:
        raise ValidationFailedError("Ledger reversal is not supported on system pages.")
    _check_version(handle, payload.version)
    if handle.status is not RecordStatus.ACTIVE:
        raise ValidationFailedError(
            f"Only an ACTIVE record can be reversed (this one is {handle.status.value})."
        )

    old_data = dict(handle.data)
    await session.execute(
        update(Record)
        .where(Record.id == handle.id)
        .values(status=RecordStatus.REVERSED, updated_by=ctx.user_id, version=handle.version + 1)
    )
    reversed_handle = await get_row(session, page, columns, handle.id, ctx.company_id)
    assert reversed_handle is not None

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="RECORD_REVERSE",
        entity_type="record",
        entity_id=handle.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        old_data=old_data,
        new_data={"status": RecordStatus.REVERSED.value},
    )

    replacement: RecordHandle | None = None
    if payload.data is not None:
        create_payload = CreateRecordRequest(
            occurred_at=payload.occurred_at or handle.occurred_at,
            store_id=payload.store_id,
            data=payload.data,
        )
        replacement = await create_record(session, ctx, page, columns, create_payload)
        await session.execute(
            update(Record).where(Record.id == replacement.id).values(reverses_id=handle.id)
        )
        refetched = await get_row(session, page, columns, replacement.id, ctx.company_id)
        assert refetched is not None
        refetched.data = formula_service.apply_formulas(columns, refetched.data)
        replacement = refetched

    reversed_handle.data = formula_service.apply_formulas(columns, reversed_handle.data)
    return reversed_handle, replacement
