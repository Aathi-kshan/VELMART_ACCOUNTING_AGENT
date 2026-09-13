"""Storage dispatch — one interface over two backends (plan section 3.5,
"the same code path... reusing record_service, not a parallel one").

An Owner-created page's rows live in the generic `records` table: platform
columns plus a JSONB `data` blob, some of it mirrored into projection columns
for indexed filtering. A system page's rows live in one of six native
tables (`app/models/business/`) with real typed columns — `page_column.key`
is chosen to equal the native column name, so `cheques.page_columns` has a
row keyed `cheque_status`, not `status` (reserved for the platform lifecycle
field, docs/API.md §1.7).

Everything in `record_service.py`/`query_service.py` goes through this
module rather than referencing `Record` or a business model directly, so
that "does an endpoint behave identically for both backends" is a property
of this one file, not something each caller has to get right independently
(`test_storage_parity` is the test that actually proves it).

`BusinessTableMixin` (`app/db/base.py`) was deliberately built to mirror
`Record`'s platform columns by name — `business_date`, `occurred_at`,
`status`, `version`, `created_by`, ... — so most of the platform-level
comparisons in `query_service.py` (sort by `business_date`, tiebreak by
`id`) work identically on either model with no branching at all. Only three
things genuinely differ, and this module is where each one lives: how a
column's *value* is read/written (JSONB path vs. a real column), what the
tenant-scoping WHERE clause looks like (`page_id` doesn't exist on a native
table — a table backs exactly one page, so `company_id` alone is enough),
and that native rows carry no `page_id` column at all.

This module never validates and never commits — callers (`record_service.py`)
already have a fully-validated, Python-typed payload by the time they call
here; this only decides *where* and *how* to write or read it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, Numeric, cast, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import ColumnElement

from app.core.errors import ValidationFailedError
from app.core.expressions.parser import parse_column_formula
from app.core.expressions.sql_compiler import compile_formula_to_sql
from app.core.money import format_money
from app.db.base import RecordStatus
from app.models.business import CashLedger, Cheque, DailyRevenue, EmployeeSalary, Expense, Purchase
from app.models.page import Page
from app.models.page_column import ColumnType, PageColumn
from app.models.record import Record
from app.repositories.base import get_for_company

#: `page.storage_table` -> the ORM class backing it.
STORAGE_MODELS: dict[str, type[DeclarativeBase]] = {
    "employee_salaries": EmployeeSalary,
    "purchases": Purchase,
    "expenses": Expense,
    "daily_revenue": DailyRevenue,
    "cash_ledger": CashLedger,
    "cheques": Cheque,
}

#: Postgres `GENERATED ALWAYS AS (...) STORED` columns (declared via
#: SQLAlchemy `Computed(...)` in the business models) — rejected in write
#: bodies (plan section 3.5.8), always present on read. Deliberately not
#: modeled as `ColumnType.FORMULA` (that's app-evaluated on read, P4; these
#: are DB-evaluated and already correct today) or a new closed-list type.
GENERATED_COLUMNS: dict[str, frozenset[str]] = {
    "daily_revenue": frozenset({"total_revenue"}),
    "cash_ledger": frozenset({"total_amount"}),
}


@dataclass
class RecordHandle:
    """The one shape `record_service.py`/`query_service.py`/`RecordOut` deal
    with, regardless of which table a row actually lives in."""

    id: uuid.UUID
    company_id: uuid.UUID
    page_id: uuid.UUID
    store_id: uuid.UUID | None
    occurred_at: datetime
    business_date: date
    status: RecordStatus
    data: dict[str, Any]
    needs_review: bool
    version: int
    created_by: uuid.UUID
    updated_by: uuid.UUID | None
    is_deleted: bool
    #: The record this one is a reversal replacement for (P4 §8) — always
    #: `None` on a native/system-table row: `BusinessTableMixin` has no such
    #: column (reversal is scoped to Owner-created generic pages only, see
    #: `record_service.reverse_record`'s own scope check).
    reverses_id: uuid.UUID | None
    #: The real ORM instance — an escape hatch for the rare caller that needs
    #: it directly, not a habit.
    row: Any


def model_for(page: Page) -> type[DeclarativeBase]:
    if page.storage_table:
        return STORAGE_MODELS[page.storage_table]
    return Record


def generated_columns_for(page: Page) -> frozenset[str]:
    if not page.storage_table:
        return frozenset()
    return GENERATED_COLUMNS.get(page.storage_table, frozenset())


def to_wire_value(column: PageColumn, value: Any) -> Any:
    """Every value in a `RecordHandle.data` (and so every `RecordOut.data`)
    is wire format — a string for money, ISO text for dates — never a Python
    `Decimal`/`date` and never a JSON number (plan section 9.1). Used on the
    way in (generic pages, before it goes into JSONB) and on the way out
    (native pages, reading real typed columns back out)."""
    if value is None:
        return None
    if column.data_type is ColumnType.CURRENCY:
        return format_money(value)
    if column.data_type in (ColumnType.NUMBER, ColumnType.PERCENT):
        return str(value)
    if column.data_type in (ColumnType.DATE, ColumnType.DATETIME):
        return value.isoformat() if hasattr(value, "isoformat") else value
    if column.data_type in (ColumnType.RECORD_REF, ColumnType.STORE_REF, ColumnType.USER_REF):
        return str(value)
    return value


def _handle_from_record(record: Record) -> RecordHandle:
    return RecordHandle(
        id=record.id,
        company_id=record.company_id,
        page_id=record.page_id,
        store_id=record.store_id,
        occurred_at=record.occurred_at,
        business_date=record.business_date,
        status=record.status,
        data=dict(record.data),
        needs_review=record.needs_review,
        version=record.version,
        created_by=record.created_by,
        updated_by=record.updated_by,
        is_deleted=record.is_deleted,
        reverses_id=record.reverses_id,
        row=record,
    )


def _handle_from_native(row: Any, page: Page, columns: list[PageColumn]) -> RecordHandle:
    data = {c.key: to_wire_value(c, getattr(row, c.key, None)) for c in columns}
    return RecordHandle(
        id=row.id,
        company_id=row.company_id,
        page_id=page.id,
        store_id=row.store_id,
        occurred_at=row.occurred_at,
        business_date=row.business_date,
        status=row.status,
        data=data,
        needs_review=row.needs_review,
        version=row.version,
        created_by=row.created_by,
        updated_by=row.updated_by,
        is_deleted=row.is_deleted,
        reverses_id=None,
        row=row,
    )


def to_handle(row: Any, page: Page, columns: list[PageColumn]) -> RecordHandle:
    if page.storage_table:
        return _handle_from_native(row, page, columns)
    return _handle_from_record(row)


# --------------------------------------------------------------------------
# Column resolution — the injection-safety boundary (query_service.py)
# --------------------------------------------------------------------------

#: `needs_review`/`status` are real columns on *both* backends (`Record` and
#: every `BusinessTableMixin` subclass) but are never entries in a page's own
#: `page_columns` — the review queue (P4 §9) needs them filterable/sortable
#: through the same `resolve_column` every other key already goes through,
#: so this is checked before falling back to page-column resolution.
_PLATFORM_FIELD_TYPES: dict[str, ColumnType] = {
    "needs_review": ColumnType.BOOLEAN,
    "status": ColumnType.SELECT,
}


def _platform_column(key: str) -> PageColumn:
    """A synthetic, never-persisted `PageColumn` — every caller of
    `resolve_column` (filter/sort/aggregate coercion, response formatting)
    keys off a `PageColumn`'s `data_type`, so this is the cheapest way to
    let a platform field ride the exact same path a real column already
    does, rather than a second set of branches in every caller."""
    config = {"options": [s.value for s in RecordStatus]} if key == "status" else {}
    return PageColumn(
        key=key, name=key, data_type=_PLATFORM_FIELD_TYPES[key], position=-1, config=config
    )


def resolve_column(
    page: Page, columns_by_key: dict[str, PageColumn], key: str
) -> tuple[ColumnElement[Any], PageColumn]:
    if key in _PLATFORM_FIELD_TYPES:
        return getattr(model_for(page), key), _platform_column(key)

    column = columns_by_key.get(key)
    if column is None:
        raise ValidationFailedError(f"Unknown column: {key!r}")

    if column.data_type is ColumnType.FORMULA:
        # Compiles to SQL rather than the row-bounded Python evaluator
        # (`app/services/formula_service.py`) because filter/sort/aggregate
        # conceptually span every matching row, not a `limit`-capped page.
        # Recursing back into `resolve_column` for the formula's own
        # dependencies (a plain column, or another formula) is safe because
        # `formula_service.check_for_cycles` already guarantees termination
        # at save time.
        parsed = parse_column_formula(column, list(columns_by_key.values()))

        def _resolve(dep_key: str) -> ColumnElement[Any]:
            expr, _ = resolve_column(page, columns_by_key, dep_key)
            return expr

        return compile_formula_to_sql(parsed, _resolve), column

    if page.storage_table:
        # A real, already-typed column — no JSONB path, no projection slot
        # bookkeeping, since indexing is native.
        return getattr(model_for(page), key), column

    slot = page.projection_map.get(key)
    if slot:
        return getattr(Record, slot), column

    raw = Record.data[key].astext
    if column.data_type in (ColumnType.NUMBER, ColumnType.CURRENCY, ColumnType.PERCENT):
        return cast(raw, Numeric), column
    if column.data_type in (ColumnType.DATE, ColumnType.DATETIME):
        return cast(raw, Date), column
    if column.data_type is ColumnType.BOOLEAN:
        return cast(raw, Boolean), column
    return raw, column


def base_conditions(page: Page) -> list[ColumnElement[bool]]:
    """The tenant/page-scoping WHERE clause every query starts from."""
    model = model_for(page)
    if page.storage_table:
        return [model.company_id == page.company_id, model.is_deleted.is_(False)]  # type: ignore[attr-defined]
    return [model.page_id == page.id, model.is_deleted.is_(False)]  # type: ignore[attr-defined]


# --------------------------------------------------------------------------
# CRUD — every function below takes a *fully validated, Python-typed,
# already-merged* payload. Nothing here parses, coerces, or re-derives.
# --------------------------------------------------------------------------


def _populate_projections(page: Page, validated: dict[str, Any]) -> dict[str, Any]:
    projections: dict[str, Any] = {}
    for key, slot in page.projection_map.items():
        value = validated.get(key)
        if value is not None and slot.startswith("date_") and isinstance(value, datetime):
            value = value.date()
        projections[slot] = value
    return projections


async def create_row(
    session: AsyncSession,
    page: Page,
    columns: list[PageColumn],
    *,
    company_id: uuid.UUID,
    store_id: uuid.UUID | None,
    occurred_at: datetime,
    business_date: date,
    validated: dict[str, Any],
    created_by: uuid.UUID,
    client_uuid: uuid.UUID | None,
    source: str = "APP",
    needs_review: bool = False,
) -> RecordHandle:
    if page.storage_table:
        model = STORAGE_MODELS[page.storage_table]
        # Only non-None values are passed through: a column that is NOT NULL
        # with a server-side default (e.g. purchases.entry_time) must be
        # *omitted* from the INSERT to get that default, not explicitly set
        # to NULL — the two are different things to Postgres.
        business_kwargs = {k: v for k, v in validated.items() if v is not None}
        row = model(
            company_id=company_id,
            store_id=store_id,
            occurred_at=occurred_at,
            business_date=business_date,
            created_by=created_by,
            client_uuid=client_uuid,
            source=source,
            needs_review=needs_review,
            **business_kwargs,
        )
        session.add(row)
        await session.flush()
        return _handle_from_native(row, page, columns)

    columns_by_key = {c.key: c for c in columns}
    wire_data = {key: to_wire_value(columns_by_key[key], value) for key, value in validated.items()}
    record = Record(
        company_id=company_id,
        page_id=page.id,
        store_id=store_id,
        occurred_at=occurred_at,
        business_date=business_date,
        data=wire_data,
        created_by=created_by,
        client_uuid=client_uuid,
        source=source,
        needs_review=needs_review,
        **_populate_projections(page, validated),
    )
    session.add(record)
    await session.flush()
    return _handle_from_record(record)


async def get_row(
    session: AsyncSession,
    page: Page,
    columns: list[PageColumn],
    record_id: uuid.UUID,
    company_id: uuid.UUID,
) -> RecordHandle | None:
    model = model_for(page)
    if page.storage_table:
        result = await session.execute(
            select(model).where(model.id == record_id, model.company_id == company_id)  # type: ignore[attr-defined]
        )
    else:
        result = await session.execute(
            select(model).where(
                model.id == record_id,  # type: ignore[attr-defined]
                model.page_id == page.id,  # type: ignore[attr-defined]
                model.company_id == company_id,  # type: ignore[attr-defined]
            )
        )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return to_handle(row, page, columns)


async def find_record(
    session: AsyncSession, company_id: uuid.UUID, record_id: uuid.UUID, system_pages: list[Page]
) -> Page | None:
    """Locate which page (and so which table) a bare record id belongs to.

    `GET/PATCH/DELETE /records/{id}` carry no `page_id` — an established,
    page-agnostic contract from P3 — so this tries the generic `records`
    table first (the common case, one indexed lookup) and only falls
    through to each system page's own native table if that misses. At most
    seven cheap primary-key-only existence checks, worst case; callers who
    already know the page (create, and any page-scoped list/query) never
    take this path. Deliberately returns just the `Page`, not a row or
    handle — every caller needs that page's live columns anyway (to decide
    what's readable/writable right now), so it always follows up with
    `get_row`, which does one fresh, fully-typed fetch rather than this
    function threading a partially-built one through.
    """
    result = await session.execute(
        select(Record.page_id).where(Record.id == record_id, Record.company_id == company_id)
    )
    page_id = result.scalar_one_or_none()
    if page_id is not None:
        return await get_for_company(session, Page, page_id, company_id)

    for page in system_pages:
        model = STORAGE_MODELS[page.storage_table]  # type: ignore[index]
        result = await session.execute(
            select(model.id).where(model.id == record_id, model.company_id == company_id)  # type: ignore[attr-defined]
        )
        if result.scalar_one_or_none() is not None:
            return page

    return None


async def update_row(
    session: AsyncSession,
    page: Page,
    handle: RecordHandle,
    columns: list[PageColumn],
    *,
    validated: dict[str, Any],
    occurred_at: datetime,
    store_id: uuid.UUID | None,
    business_date: date,
    updated_by: uuid.UUID,
    needs_review: bool | None = None,
) -> RecordHandle:
    """`validated` is the *full*, merged, Python-typed record — not a delta.
    Every business column is (re)written unconditionally, `None` included:
    unlike `create_row`'s "omit `None` so a NOT-NULL server_default can
    apply" rule, an update's `validated` already reflects every column's
    intended final value, so an explicit `None` here means the caller wants
    that nullable column cleared, not left alone. This is also simpler than
    tracking which keys actually changed, and updates are not a
    high-frequency path where that simplicity costs anything real.

    `needs_review` defaults to `None` (left untouched) rather than `False`:
    no caller of this function recomputes it (the feature that used to —
    `page_validations` — has been removed), so an ordinary edit must never
    silently clear a flag a record already carries."""
    values: dict[str, Any] = {
        "version": handle.version + 1,
        "updated_by": updated_by,
        "occurred_at": occurred_at,
        "business_date": business_date,
    }
    if needs_review is not None:
        values["needs_review"] = needs_review
    if store_id is not None:
        values["store_id"] = store_id

    model = model_for(page)
    if page.storage_table:
        values.update(validated)
        await session.execute(update(model).where(model.id == handle.id).values(**values))  # type: ignore[attr-defined]
    else:
        columns_by_key = {c.key: c for c in columns}
        wire_data = {
            key: to_wire_value(columns_by_key[key], value) for key, value in validated.items()
        }
        values["data"] = wire_data
        values.update(_populate_projections(page, validated))
        await session.execute(update(Record).where(Record.id == handle.id).values(**values))

    updated = await get_row(session, page, columns, handle.id, handle.company_id)
    assert updated is not None
    return updated


async def soft_delete_row(
    session: AsyncSession, page: Page, handle: RecordHandle, *, reason: str, updated_by: uuid.UUID
) -> None:
    model = model_for(page)
    await session.execute(
        update(model)
        .where(model.id == handle.id)  # type: ignore[attr-defined]
        .values(is_deleted=True, deleted_reason=reason, updated_by=updated_by)
    )


