"""Query, aggregate, and formula tools (plan section 16.4, P7.4) — the core
of "AI read and analysis". Every number these tools return is computed by
Postgres (`query_service.py`) or by the same safe expression evaluator a
page's own FORMULA columns use (`app/core/expressions/`) — never by the
model itself.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools._shared import resolve_page
from app.ai.tools.registry import register_tool
from app.core.context import SecurityContext
from app.core.errors import ExpressionSecurityError, ValidationFailedError
from app.core.expressions.evaluator import FormulaEvaluationError, evaluate
from app.core.expressions.parser import parse_expression
from app.schemas.common import MAX_PAGE_LIMIT, QueryFilter, SortSpec
from app.schemas.record import AggregateMetric, AggregatePeriod, AggregateRequest, QueryRequest
from app.services import page_service, query_service


def _record_items(items: list[Any]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in items]


# --------------------------------------------------------------------------
# query_records / filter_records / sort_records
# --------------------------------------------------------------------------


class QueryRecordsParams(BaseModel):
    page_key: str
    filters: list[QueryFilter] = Field(default_factory=list)
    sort: list[SortSpec] = Field(default_factory=list)
    search: str | None = None
    limit: int = Field(default=50, ge=1, le=MAX_PAGE_LIMIT)


async def query_records(
    *, ctx: SecurityContext, session: AsyncSession, params: QueryRecordsParams
) -> dict[str, Any]:
    page, columns = await resolve_page(session, ctx, params.page_key)
    request = QueryRequest(
        filters=params.filters, sort=params.sort, search=params.search, limit=params.limit
    )
    result = await query_service.query_records(session, page, columns, request)
    return {
        "page_key": page.key,
        "items": _record_items(result.items),
        "has_more": result.has_more,
    }


register_tool(
    query_records,
    name="query_records",
    description=(
        "Look up records on one page, with optional filters, sort, and text "
        "search. Prefer aggregate_records for totals — only use this to see "
        "individual rows."
    ),
    params_model=QueryRecordsParams,
)


class FilterRecordsParams(BaseModel):
    page_key: str
    filters: list[QueryFilter] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=MAX_PAGE_LIMIT)


async def filter_records(
    *, ctx: SecurityContext, session: AsyncSession, params: FilterRecordsParams
) -> dict[str, Any]:
    page, columns = await resolve_page(session, ctx, params.page_key)
    request = QueryRequest(filters=params.filters, limit=params.limit)
    result = await query_service.query_records(session, page, columns, request)
    return {
        "page_key": page.key,
        "items": _record_items(result.items),
        "has_more": result.has_more,
    }


register_tool(
    filter_records,
    name="filter_records",
    description="Look up records on one page matching one or more filters, with no sort applied.",
    params_model=FilterRecordsParams,
)


class SortRecordsParams(BaseModel):
    page_key: str
    sort: list[SortSpec] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=MAX_PAGE_LIMIT)


async def sort_records(
    *, ctx: SecurityContext, session: AsyncSession, params: SortRecordsParams
) -> dict[str, Any]:
    page, columns = await resolve_page(session, ctx, params.page_key)
    request = QueryRequest(sort=params.sort, limit=params.limit)
    result = await query_service.query_records(session, page, columns, request)
    return {
        "page_key": page.key,
        "items": _record_items(result.items),
        "has_more": result.has_more,
    }


register_tool(
    sort_records,
    name="sort_records",
    description="Look up records on one page in a given sort order, with no filters applied.",
    params_model=SortRecordsParams,
)


# --------------------------------------------------------------------------
# search_records — page-scoped, or fanned out across every page
# --------------------------------------------------------------------------


class SearchRecordsParams(BaseModel):
    query: str
    page_key: str | None = Field(
        default=None, description="Limit the search to one page; omit to search every page."
    )
    limit: int = Field(default=50, ge=1, le=MAX_PAGE_LIMIT)


async def search_records(
    *, ctx: SecurityContext, session: AsyncSession, params: SearchRecordsParams
) -> dict[str, Any]:
    if params.page_key is not None:
        page, columns = await resolve_page(session, ctx, params.page_key)
        request = QueryRequest(search=params.query, limit=params.limit)
        result = await query_service.query_records(session, page, columns, request)
        return {"matches_by_page": {page.key: _record_items(result.items)}}

    pages = await page_service.list_pages(session, ctx)
    matches: dict[str, list[dict[str, Any]]] = {}
    remaining = params.limit
    for page in pages:
        if remaining <= 0:
            break
        columns = await page_service.get_page_columns(session, page.id)
        request = QueryRequest(search=params.query, limit=remaining)
        result = await query_service.query_records(session, page, columns, request)
        if result.items:
            matches[page.key] = _record_items(result.items)
            remaining -= len(result.items)
    return {"matches_by_page": matches}


register_tool(
    search_records,
    name="search_records",
    description=(
        "Free-text search for a value across one page, or (if page_key is "
        "omitted) across every page in this business."
    ),
    params_model=SearchRecordsParams,
)


# --------------------------------------------------------------------------
# aggregate_records
# --------------------------------------------------------------------------


class AggregateRecordsParams(BaseModel):
    page_key: str
    metric: AggregateMetric
    column_key: str | None = Field(
        default=None, description="Required for every metric except 'count'."
    )
    group_by: str | None = None
    period: AggregatePeriod = "all_time"
    filters: list[QueryFilter] = Field(default_factory=list)


async def aggregate_records(
    *, ctx: SecurityContext, session: AsyncSession, params: AggregateRecordsParams
) -> dict[str, Any]:
    page, columns = await resolve_page(session, ctx, params.page_key)
    request = AggregateRequest(
        metric=params.metric,
        column=params.column_key,
        group_by=params.group_by,
        period=params.period,
        filters=params.filters,
    )
    result = await query_service.aggregate(session, page, columns, request)
    return {
        "page_key": page.key,
        "value": result.value,
        "record_count": result.record_count,
        "period": {
            "from": result.period.from_.isoformat() if result.period.from_ else None,
            "to": result.period.to.isoformat() if result.period.to else None,
        },
        "groups": [{"key": g.key, "value": g.value, "count": g.count} for g in result.groups],
    }


register_tool(
    aggregate_records,
    name="aggregate_records",
    description=(
        "Compute a sum, average, count, min, or max over one page's "
        "records, computed by the database — always prefer this over "
        "fetching individual records and adding them up yourself."
    ),
    params_model=AggregateRecordsParams,
)


# --------------------------------------------------------------------------
# calculate_formula
# --------------------------------------------------------------------------


class CalculateFormulaParams(BaseModel):
    expression: str = Field(description="e.g. '(current - previous) / previous * 100'")
    operands: dict[str, str | float | int | bool] = Field(
        description="Named values the expression may reference, e.g. {'current': '1200.00'}."
    )


async def calculate_formula(
    *, ctx: SecurityContext, session: AsyncSession, params: CalculateFormulaParams
) -> dict[str, Any]:
    """Evaluates an ad-hoc expression over values the model already
    retrieved (e.g. via aggregate_records) — through the same whitelist
    parser/evaluator a page's own FORMULA columns use, never Python `eval`."""
    available = frozenset(params.operands)
    try:
        parsed = parse_expression(params.expression, available)
    except ExpressionSecurityError as exc:
        raise ValidationFailedError(str(exc)) from exc

    typed_operands: dict[str, Any] = {}
    for key, value in params.operands.items():
        if isinstance(value, bool):
            typed_operands[key] = value
            continue
        try:
            typed_operands[key] = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValidationFailedError(f"{key!r} is not a valid number.") from exc

    try:
        result = evaluate(parsed, typed_operands)
    except FormulaEvaluationError as exc:
        raise ValidationFailedError(str(exc)) from exc

    return {"result": str(result) if isinstance(result, Decimal) else result}


register_tool(
    calculate_formula,
    name="calculate_formula",
    description=(
        "Combine numbers you already retrieved (e.g. a percentage or "
        "difference) using a safe expression — never do this arithmetic "
        "yourself."
    ),
    params_model=CalculateFormulaParams,
)
