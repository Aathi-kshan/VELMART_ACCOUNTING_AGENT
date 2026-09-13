"""Query, aggregation, and column-value discovery over one page's records
(plan sections 3.8, 3.9, 10.4, 21.2; docs/API.md §5) — the same code path
for an Owner-created page or a system page (Employee Salary, Purchases,
Expenses, Daily Revenue, Cash Ledger, Cheques), via `app/repositories/
records.py`'s storage dispatch.

The one safety rule this module exists to enforce ("injection-proof",
`test_query_filters`): a `column` string from the request body is only ever
used as a **dict-key lookup** into a whitelist built from that page's own
`page_columns` — an unknown key is a plain 422, never reaches SQL at all.
The resolved value is always a real SQLAlchemy column expression —
`app/repositories/records.py`'s `resolve_column` returns a real typed
column for a system page, or (for a generic page, exactly as before) a
`Record` projection column, or `Record.data[key].astext` (SQLAlchemy's
JSONB comparator, which binds `key` as a parameter — it never
string-formats it) cast to the column's real type. Filter/sort *values* go
through SQLAlchemy bind parameters the same as any other query in this
codebase.

Pagination is keyset, not `OFFSET` (stable under concurrent inserts): each
sort key carries a matching pair of functions to read a fetched row's value
(`row_value`) and to parse that same value back out of an opaque cursor
string (`parse_cursor`) — symmetric by construction, since both ultimately
go through `_coerce` for page-column keys. `row_value` reads straight off
the raw ORM row (a `Record` or a native business model instance) rather
than a `RecordHandle`, since the row is what pagination actually fetches;
`RecordHandle` only enters the picture when building the response body.
"""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import partial
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Text, and_, cast, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.core.dates import COMPANY_TIMEZONE
from app.core.errors import ValidationFailedError
from app.core.money import MoneyError, format_money, parse_money
from app.db.base import RecordStatus
from app.models.page import Page
from app.models.page_column import ColumnType, PageColumn
from app.models.record import Record
from app.repositories.records import (
    base_conditions,
    model_for,
    resolve_column,
    to_handle,
    to_wire_value,
)
from app.schemas.common import Paginated, QueryFilter, SortSpec
from app.schemas.record import (
    AggregateGroup,
    AggregatePeriodRange,
    AggregateRequest,
    AggregateResponse,
    QueryRequest,
    RecordOut,
    RunningBalanceEntry,
)
from app.services import formula_service


def _coerce(column: PageColumn, raw: Any) -> Any:
    """Wire-format value (as stored in `records.data`, or as supplied in a
    filter/cursor), OR an already Python-typed value (a native table's real
    column) -> the typed Python value comparable against `resolve_column`'s
    expression. Every branch here happens to accept both forms already —
    `parse_money`/`Decimal(str(...))` take a `Decimal` as readily as a
    string, `date`/`datetime` pass through their own type unchanged — so
    this one function serves both backends without branching on which."""
    if raw is None:
        return None
    try:
        if column.data_type is ColumnType.CURRENCY:
            return parse_money(raw)
        if column.data_type in (ColumnType.NUMBER, ColumnType.PERCENT):
            return Decimal(str(raw))
        if column.data_type is ColumnType.DATE:
            return raw if isinstance(raw, date) else date.fromisoformat(str(raw))
        if column.data_type is ColumnType.DATETIME:
            return raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
        if column.data_type is ColumnType.BOOLEAN:
            return raw if isinstance(raw, bool) else str(raw).lower() == "true"
        if column.data_type is ColumnType.FORMULA:
            # Every function in the formula grammar (§2) operates in
            # `Decimal` — a bare `str(raw)` here (this function's fallback
            # for every other type) would bind as VARCHAR against the
            # compiled SQL expression's NUMERIC type and fail outright
            # (`operator does not exist: numeric > character varying`).
            return None if raw is None else Decimal(str(raw))
    except (InvalidOperation, ValueError, MoneyError) as exc:
        raise ValidationFailedError(f"{column.name}: {exc}") from exc
    return str(raw)


def _encode_scalar(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


# --------------------------------------------------------------------------
# Filters
# --------------------------------------------------------------------------


def _apply_filter(stmt: Any, expr: ColumnElement[Any], column: PageColumn, f: QueryFilter) -> Any:
    if f.op == "is_null":
        return stmt.where(expr.is_(None))
    if f.op == "between":
        if not isinstance(f.value, list) or len(f.value) != 2:
            raise ValidationFailedError(f"{column.name}: 'between' needs a 2-element value.")
        lo, hi = (_coerce(column, v) for v in f.value)
        return stmt.where(expr.between(lo, hi))
    if f.op == "in":
        if not isinstance(f.value, list):
            raise ValidationFailedError(f"{column.name}: 'in' needs a list value.")
        return stmt.where(expr.in_([_coerce(column, v) for v in f.value]))
    if f.op == "contains":
        return stmt.where(expr.ilike(f"%{_coerce(column, f.value)}%"))

    value = _coerce(column, f.value)
    match f.op:
        case "eq":
            return stmt.where(expr == value)
        case "neq":
            return stmt.where(expr != value)
        case "gt":
            return stmt.where(expr > value)
        case "gte":
            return stmt.where(expr >= value)
        case "lt":
            return stmt.where(expr < value)
        case "lte":
            return stmt.where(expr <= value)
        case _:  # pragma: no cover - Literal type already restricts this
            raise ValidationFailedError(f"Unsupported operator: {f.op!r}")


def _apply_all_filters(
    stmt: Any, page: Page, columns_by_key: dict[str, PageColumn], filters: list[QueryFilter]
) -> Any:
    for f in filters:
        expr, column = resolve_column(page, columns_by_key, f.column)
        stmt = _apply_filter(stmt, expr, column, f)
    return stmt


def _apply_search(stmt: Any, page: Page, columns: list[PageColumn], search: str | None) -> Any:
    if not search:
        return stmt
    if not page.storage_table:
        return stmt.where(cast(Record.data, Text).ilike(f"%{search}%"))
    model = model_for(page)
    text_keys = [c.key for c in columns if c.data_type in (ColumnType.TEXT, ColumnType.LONG_TEXT)]
    if not text_keys:
        return stmt.where(false())
    return stmt.where(or_(*(getattr(model, key).ilike(f"%{search}%") for key in text_keys)))


def apply_filters_and_search(
    stmt: Any,
    page: Page,
    columns: list[PageColumn],
    filters: list[QueryFilter],
    search: str | None,
) -> Any:
    """The public entry point for a caller outside this module (`csv_service.py`'s
    export) that needs the same injection-safe filter/search narrowing
    `query_records` applies internally — reused rather than re-implemented,
    so there is exactly one place a `column` string is ever resolved against
    a page's live schema."""
    columns_by_key = {c.key: c for c in columns}
    stmt = _apply_all_filters(stmt, page, columns_by_key, filters)
    return _apply_search(stmt, page, columns, search)


# --------------------------------------------------------------------------
# Keyset pagination
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _SortKey:
    #: A real column expression — a platform column (mapped attribute, on
    #: whichever model backs this page) or a resolved projection/JSONB-path/
    #: native-column expression. Typed `Any` because SQLAlchemy's
    #: mapped-attribute type and its Core `ColumnElement` type aren't
    #: structurally interchangeable to mypy, even though both support the
    #: same `.desc()`/`==`/`<` operations used here.
    expr: Any
    direction: str
    row_value: Callable[[Any], Any]
    parse_cursor: Callable[[str], Any]


def _platform_sort_key(page: Page, name: str, direction: str) -> _SortKey:
    model = model_for(page)
    if name == "business_date":
        return _SortKey(
            model.business_date, direction, lambda r: r.business_date, date.fromisoformat  # type: ignore[attr-defined]
        )
    if name == "occurred_at":
        return _SortKey(
            model.occurred_at, direction, lambda r: r.occurred_at, datetime.fromisoformat  # type: ignore[attr-defined]
        )
    raise ValidationFailedError(f"Unknown sort column: {name!r}")


#: Real columns on *both* backends (`Record` and every `BusinessTableMixin`
#: subclass), but never nested inside a generic page's JSONB `data` — the
#: same set `resolve_column` special-cases (P4 §9). `_row_value`'s generic
#: branch below reads `row.data.get(key)` for a real page column, which
#: would always miss these; they need `getattr(row, key)` unconditionally,
#: on both backends, like `business_date`/`occurred_at` already get.
_PLATFORM_ROW_FIELDS = frozenset({"needs_review", "status"})


def _row_value(
    page: Page, columns: list[PageColumn], column: PageColumn, key: str, row: Any
) -> Any:
    if column.data_type is ColumnType.FORMULA:
        # Never stored, so there is no `row.data[key]` to read back — the
        # cursor has to carry the same computed value the SQL-compiled sort
        # expression just ordered by, or keyset pagination would resume from
        # `None` and silently drop the rest of the page.
        handle = to_handle(row, page, columns)
        computed = formula_service.apply_formulas(columns, handle.data)
        return _coerce(column, computed.get(key))
    if key in _PLATFORM_ROW_FIELDS:
        return _coerce(column, getattr(row, key))
    raw = getattr(row, key) if page.storage_table else row.data.get(key)
    return _coerce(column, raw)


def _column_sort_key(
    page: Page, columns: list[PageColumn], columns_by_key: dict[str, PageColumn], spec: SortSpec
) -> _SortKey:
    if spec.column in ("business_date", "occurred_at"):
        return _platform_sort_key(page, spec.column, spec.direction)
    expr, column = resolve_column(page, columns_by_key, spec.column)
    return _SortKey(
        expr,
        spec.direction,
        partial(_row_value, page, columns, column, spec.column),
        partial(_coerce, column),
    )


def _id_tiebreaker(page: Page) -> _SortKey:
    model = model_for(page)
    return _SortKey(model.id, "desc", lambda r: r.id, uuid.UUID)  # type: ignore[attr-defined]


def _encode_cursor(keys: list[_SortKey], row: Any) -> str:
    values = [_encode_scalar(k.row_value(row)) for k in keys]
    return base64.urlsafe_b64encode(json.dumps(values).encode()).decode()


def _decode_cursor(keys: list[_SortKey], cursor: str) -> list[Any]:
    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if not isinstance(raw, list) or len(raw) != len(keys):
            raise ValueError("cursor shape does not match the current sort")
        return [k.parse_cursor(v) for k, v in zip(keys, raw, strict=True)]
    except ValidationFailedError:
        raise
    except Exception as exc:
        raise ValidationFailedError("Invalid or corrupted cursor.") from exc


def _keyset_predicate(keys: list[_SortKey], values: list[Any]) -> ColumnElement[bool]:
    """Standard keyset-pagination OR-of-ANDs: strictly beyond the cursor on
    the first key that differs, direction-aware."""
    clauses = []
    for i, (key, value) in enumerate(zip(keys, values, strict=True)):
        equalities = [k.expr == v for k, v in zip(keys[:i], values[:i], strict=True)]
        comparison = key.expr < value if key.direction == "desc" else key.expr > value
        clauses.append(and_(*equalities, comparison))
    return or_(*clauses)


# --------------------------------------------------------------------------
# Query
# --------------------------------------------------------------------------


async def query_records(
    session: AsyncSession, page: Page, columns: list[PageColumn], payload: QueryRequest
) -> Paginated[RecordOut]:
    columns_by_key = {c.key: c for c in columns}
    model = model_for(page)

    sort_specs = payload.sort or [
        SortSpec(column="business_date", direction="desc"),
        SortSpec(column="occurred_at", direction="desc"),
    ]
    sort_keys = [_column_sort_key(page, columns, columns_by_key, spec) for spec in sort_specs]
    sort_keys.append(_id_tiebreaker(page))

    stmt = select(model).where(*base_conditions(page))
    stmt = _apply_all_filters(stmt, page, columns_by_key, payload.filters)
    stmt = _apply_search(stmt, page, columns, payload.search)
    if payload.cursor:
        cursor_values = _decode_cursor(sort_keys, payload.cursor)
        stmt = stmt.where(_keyset_predicate(sort_keys, cursor_values))
    for key in sort_keys:
        stmt = stmt.order_by(key.expr.desc() if key.direction == "desc" else key.expr.asc())
    stmt = stmt.limit(payload.limit + 1)

    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > payload.limit
    rows = rows[: payload.limit]

    next_cursor = _encode_cursor(sort_keys, rows[-1]) if has_more and rows else None
    # Built once for the whole page, not once per row — rebuilding the
    # dynamic operand model per row would be real, avoidable overhead at a
    # full page of up to 500 records.
    formula_plan = formula_service.prepare(columns)
    items: list[RecordOut] = []
    for row in rows:
        handle = to_handle(row, page, columns)
        # Computed for the response only, never stored (plan 11.1, P4 §4).
        handle.data = formula_service.apply_prepared(formula_plan, columns, handle.data)
        items.append(RecordOut.model_validate(handle))

    return Paginated[RecordOut](items=items, next_cursor=next_cursor, has_more=has_more)


async def column_values(
    session: AsyncSession, page: Page, columns: list[PageColumn], key: str, limit: int = 100
) -> list[str]:
    columns_by_key = {c.key: c for c in columns}
    column = columns_by_key.get(key)
    if column is None:
        raise ValidationFailedError(f"Unknown column: {key!r}")

    if column.data_type in (ColumnType.SELECT, ColumnType.MULTI_SELECT):
        options = column.config.get("options") or []
        return [str(o) for o in options]

    expr, _ = resolve_column(page, columns_by_key, key)
    result = await session.execute(
        select(expr).where(*base_conditions(page), expr.is_not(None)).distinct().limit(limit)
    )
    return [str(v) for (v,) in result.all()]


# --------------------------------------------------------------------------
# Aggregate
# --------------------------------------------------------------------------

_METRIC_FUNCS: dict[str, Callable[[ColumnElement[Any]], ColumnElement[Any]]] = {
    "sum": func.sum,
    "avg": func.avg,
    "min": func.min,
    "max": func.max,
}


def _period_range(period: str) -> AggregatePeriodRange:
    today = datetime.now(tz=ZoneInfo(COMPANY_TIMEZONE)).date()
    if period == "all_time":
        return AggregatePeriodRange(from_=None, to=None)
    if period == "current_year":
        return AggregatePeriodRange(from_=today.replace(month=1, day=1), to=today)
    if period == "current_month":
        return AggregatePeriodRange(from_=today.replace(day=1), to=today)
    if period == "last_month":
        first_of_this_month = today.replace(day=1)
        last_of_last_month = first_of_this_month - timedelta(days=1)
        return AggregatePeriodRange(from_=last_of_last_month.replace(day=1), to=last_of_last_month)
    raise ValidationFailedError(f"Unknown period: {period!r}")


def _format_metric_value(value: Any, column: PageColumn | None) -> str:
    if value is None:
        return "0"
    if column is not None and column.data_type is ColumnType.CURRENCY:
        return format_money(Decimal(value))
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _apply_period(stmt: Any, page: Page, period_range: AggregatePeriodRange) -> Any:
    model = model_for(page)
    if period_range.from_ is not None:
        stmt = stmt.where(model.business_date >= period_range.from_)  # type: ignore[attr-defined]
    if period_range.to is not None:
        stmt = stmt.where(model.business_date <= period_range.to)  # type: ignore[attr-defined]
    return stmt


async def aggregate(
    session: AsyncSession, page: Page, columns: list[PageColumn], payload: AggregateRequest
) -> AggregateResponse:
    columns_by_key = {c.key: c for c in columns}
    period_range = _period_range(payload.period)
    model = model_for(page)

    metric_column: PageColumn | None = None
    if payload.metric == "count" and payload.column is None:
        metric_expr: ColumnElement[Any] = func.count()
    else:
        if payload.column is None:
            raise ValidationFailedError("column is required for this metric.")
        col_expr, metric_column = resolve_column(page, columns_by_key, payload.column)
        metric_expr = _METRIC_FUNCS.get(payload.metric, func.count)(col_expr)

    # Two independent queries sharing the same filter-building calls, rather
    # than one query's subquery feeding the other — simpler and avoids having
    # to rebind expressions built against `model` onto a derived subquery's
    # own column objects.
    total_stmt = (
        select(metric_expr, func.count()).select_from(model).where(*base_conditions(page))
    )
    total_stmt = _apply_period(total_stmt, page, period_range)
    total_stmt = _apply_all_filters(total_stmt, page, columns_by_key, payload.filters)
    total_value, total_count = (await session.execute(total_stmt)).one()

    groups: list[AggregateGroup] = []
    if payload.group_by:
        group_expr, _ = resolve_column(page, columns_by_key, payload.group_by)
        grouped_stmt = (
            select(group_expr, metric_expr, func.count())
            .select_from(model)
            .where(*base_conditions(page))
        )
        grouped_stmt = _apply_period(grouped_stmt, page, period_range)
        grouped_stmt = _apply_all_filters(grouped_stmt, page, columns_by_key, payload.filters)
        grouped_stmt = grouped_stmt.group_by(group_expr)
        for group_key, value, count in (await session.execute(grouped_stmt)).all():
            groups.append(
                AggregateGroup(
                    key=str(group_key),
                    value=_format_metric_value(value, metric_column),
                    count=count,
                )
            )

    return AggregateResponse(
        value=_format_metric_value(total_value, metric_column),
        record_count=total_count,
        period=period_range,
        groups=groups,
    )


async def running_balance(
    session: AsyncSession, page: Page, columns: list[PageColumn]
) -> list[RunningBalanceEntry]:
    """`GET /pages/{id}/running-balance` (plan section 11.5, P4 §8) — a SQL
    window function over `page.balance_column_key`, `ACTIVE` rows only, in
    the same default row order every other endpoint uses. Never stored:
    computed fresh on every call, the same principle a FORMULA column's
    value already follows."""
    if not page.balance_column_key:
        raise ValidationFailedError("This page has no balance_column_key configured.")

    columns_by_key = {c.key: c for c in columns}
    balance_expr, balance_column = resolve_column(page, columns_by_key, page.balance_column_key)
    model = model_for(page)
    cumulative = func.sum(balance_expr).over(
        order_by=(model.business_date, model.occurred_at, model.id)  # type: ignore[attr-defined]
    )

    stmt = (
        select(model.id, model.business_date, balance_expr, cumulative)  # type: ignore[attr-defined]
        .where(*base_conditions(page), model.status == RecordStatus.ACTIVE)  # type: ignore[attr-defined]
        .order_by(model.business_date, model.occurred_at, model.id)  # type: ignore[attr-defined]
    )
    result = await session.execute(stmt)
    return [
        RunningBalanceEntry(
            record_id=record_id,
            business_date=business_date,
            amount=to_wire_value(balance_column, amount) or "0.00",
            balance=to_wire_value(balance_column, balance) or "0.00",
        )
        for record_id, business_date, amount, balance in result.all()
    ]
