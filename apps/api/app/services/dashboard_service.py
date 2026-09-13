"""Daily reconciliation (plan section 3.5.11 / 12.5, docs/API.md §1.8) and
configurable dashboard widgets (plan section 15, P5).

Reconciliation reads straight from the `daily_reconciliation` view
(migration 0008) — a `SECURITY INVOKER` view, so Postgres's own
`store_scope` RLS policy on `daily_revenue`/`cash_ledger` already restricts
what a manager's totals sum to, exactly as it would querying either table
directly. No application-level store filtering happens here; `WHERE
company_id = ...` below is defense in depth (the same table's own
`tenant_isolation` policy already guarantees it), not the thing doing the
real scoping.

Access control (both `daily_revenue` and `cash_ledger` system pages must be
`view`-granted, 404 for either missing) is the router's job — this function
assumes that's already been checked and just reads.

Widget evaluation reuses `query_service.py`'s `aggregate`/`query_records`
directly for four of the five widget types — a widget's `config` embeds the
same `AggregateRequest`/`QueryRequest` shapes, not a second query language.
`TREND` is the one exception: neither existing function has day/week
bucketing, so it gets one small, contained query here rather than growing
the shared query engine for a dashboard-only need.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.core.context import SecurityContext
from app.core.errors import NotFoundError, ValidationFailedError
from app.core.money import format_money
from app.db.base import RecordStatus
from app.dependencies.guards import require_page_access
from app.models.daily_digest import DailyDigest
from app.models.dashboard_widget import DashboardWidget
from app.models.page import Page
from app.models.page_column import PageColumn
from app.repositories.base import get_for_company
from app.repositories.records import base_conditions, model_for, resolve_column
from app.schemas.common import QueryFilter
from app.schemas.dashboard import (
    BreakdownConfig,
    DailyDigestOut,
    ListConfig,
    MetricConfig,
    ReconciliationItem,
    TrendConfig,
    TrendPoint,
    WidgetCreateRequest,
    WidgetEvaluationResponse,
    WidgetSuggestion,
    WidgetUpdateRequest,
)
from app.schemas.record import AggregateRequest, QueryRequest
from app.services import page_service, query_service
from app.services.audit_service import write_audit_log
from app.services.query_service import _format_metric_value  # reuse, not reimplement


async def get_reconciliation(
    session: AsyncSession,
    ctx: SecurityContext,
    date_from: date | None,
    date_to: date | None,
) -> list[ReconciliationItem]:
    conditions = ["company_id = :company_id"]
    params: dict[str, object] = {"company_id": str(ctx.company_id)}
    if date_from is not None:
        conditions.append("business_date >= :date_from")
        params["date_from"] = date_from
    if date_to is not None:
        conditions.append("business_date <= :date_to")
        params["date_to"] = date_to

    # noqa justification: `sql` is built entirely from the two hardcoded
    # strings above, never from caller input — only their associated
    # *values* (bound as `params`) come from the request, and those go
    # through SQLAlchemy bind parameters, not string interpolation.
    sql = (
        "SELECT business_date, revenue_total, ledger_total, difference "  # noqa: S608
        f"FROM daily_reconciliation WHERE {' AND '.join(conditions)} "
        "ORDER BY business_date"
    )
    query = text(sql)
    result = await session.execute(query, params)
    return [
        ReconciliationItem(
            business_date=row.business_date,
            revenue_total=format_money(row.revenue_total),
            ledger_total=format_money(row.ledger_total),
            difference=format_money(row.difference),
        )
        for row in result
    ]


# --------------------------------------------------------------------------
# Widgets (plan section 15, P5)
# --------------------------------------------------------------------------

_CONFIG_MODELS = {
    "METRIC": MetricConfig,
    "TREND": TrendConfig,
    "BREAKDOWN": BreakdownConfig,
    "LIST": ListConfig,
    # REVIEW_QUEUE takes no widget-specific config — its query is fixed
    # (`needs_review = true` on the widget's own page).
}


async def _resolve_page(session: AsyncSession, ctx: SecurityContext, page_key: str) -> Page:
    page = await page_service.get_page_by_key(session, ctx.company_id, page_key)
    if page is None:
        raise ValidationFailedError(f"No such page: {page_key!r}.")
    return page


def _validate_config(widget_type: str, columns: list[PageColumn], config: dict) -> dict:
    """Parses `config` into the type-specific model (catching shape
    mistakes) and confirms every column it names is real on this page — the
    same "fail at save, never at read" principle every other schema
    validation in this codebase already follows. Returns the normalized
    dict `create_widget`/`update_widget` actually store."""
    model = _CONFIG_MODELS.get(widget_type)
    if model is None:
        return {}
    try:
        parsed = model(**config)
    except Exception as exc:  # pydantic.ValidationError, not imported just to catch by name
        raise ValidationFailedError(f"Invalid config for {widget_type}: {exc}") from exc

    keys = {c.key for c in columns}
    referenced = {
        key
        for key in (
            getattr(parsed, "column", None),
            getattr(parsed, "group_by", None),
        )
        if key is not None
    }
    for filter_ in getattr(parsed, "filters", []):
        referenced.add(filter_.column)
    for sort in getattr(parsed, "sort", []):
        referenced.add(sort.column)
    unknown = referenced - keys - {"needs_review", "status", "business_date", "occurred_at"}
    if unknown:
        raise ValidationFailedError(f"Unknown column(s) for this page: {sorted(unknown)}.")

    return parsed.model_dump(mode="json")


async def create_widget(
    session: AsyncSession, ctx: SecurityContext, payload: WidgetCreateRequest
) -> DashboardWidget:
    page = await _resolve_page(session, ctx, payload.page_key)
    columns = await page_service.get_page_columns(session, page.id)
    config = _validate_config(payload.widget_type, columns, payload.config)

    widget = DashboardWidget(
        company_id=ctx.company_id,
        page_id=page.id,
        title=payload.title,
        widget_type=payload.widget_type,
        config=config,
        position=payload.position,
        visible_to=payload.visible_to,
        created_by=ctx.user_id,
    )
    session.add(widget)
    await session.flush()

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="DASHBOARD_WIDGET_CREATE",
        entity_type="dashboard_widget",
        entity_id=widget.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        new_data={"title": widget.title, "widget_type": widget.widget_type},
    )
    return widget


async def get_widget(
    session: AsyncSession, ctx: SecurityContext, widget_id: uuid.UUID
) -> DashboardWidget:
    result = await session.execute(
        select(DashboardWidget).where(
            DashboardWidget.id == widget_id, DashboardWidget.company_id == ctx.company_id
        )
    )
    widget = result.scalar_one_or_none()
    if widget is None:
        raise NotFoundError("No such widget.")
    return widget


async def update_widget(
    session: AsyncSession, ctx: SecurityContext, widget_id: uuid.UUID, payload: WidgetUpdateRequest
) -> DashboardWidget:
    widget = await get_widget(session, ctx, widget_id)
    old_data = {"title": widget.title, "config": widget.config, "position": widget.position}

    if payload.title is not None:
        widget.title = payload.title
    if payload.config is not None:
        columns = await page_service.get_page_columns(session, widget.page_id)  # type: ignore[arg-type]
        widget.config = _validate_config(widget.widget_type, columns, payload.config)
    if payload.position is not None:
        widget.position = payload.position
    if payload.clear_visible_to:
        widget.visible_to = None
    elif payload.visible_to is not None:
        widget.visible_to = payload.visible_to

    await session.flush()
    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="DASHBOARD_WIDGET_UPDATE",
        entity_type="dashboard_widget",
        entity_id=widget.id,
        page_id=widget.page_id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        old_data=old_data,
        new_data={"title": widget.title, "config": widget.config, "position": widget.position},
    )
    return widget


async def delete_widget(session: AsyncSession, ctx: SecurityContext, widget_id: uuid.UUID) -> None:
    widget = await get_widget(session, ctx, widget_id)
    await session.delete(widget)
    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="DASHBOARD_WIDGET_DELETE",
        entity_type="dashboard_widget",
        entity_id=widget_id,
        page_id=widget.page_id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        old_data={"title": widget.title},
    )


async def list_widgets(session: AsyncSession, ctx: SecurityContext) -> list[DashboardWidget]:
    """Double-gated for a manager (plan section 15.3): `visible_to` (role)
    AND `view` access on the widget's own page — an Owner bypasses both,
    same convention as `page_service.get_page_for_ctx`."""
    if ctx.is_owner:
        result = await session.execute(
            select(DashboardWidget)
            .where(DashboardWidget.company_id == ctx.company_id)
            .order_by(DashboardWidget.position)
        )
        return list(result.scalars().all())

    viewable_pages = await page_service.list_pages(session, ctx)
    viewable_page_ids = {p.id for p in viewable_pages}
    result = await session.execute(
        select(DashboardWidget)
        .where(
            DashboardWidget.company_id == ctx.company_id,
            (DashboardWidget.visible_to.is_(None)) | (DashboardWidget.visible_to == ctx.role),
        )
        .order_by(DashboardWidget.position)
    )
    return [w for w in result.scalars().all() if w.page_id in viewable_page_ids]


def _metric_func(metric: str) -> Callable[[ColumnElement[Any]], ColumnElement[Any]]:
    funcs: dict[str, Callable[[ColumnElement[Any]], ColumnElement[Any]]] = {
        "sum": func.sum,
        "avg": func.avg,
        "min": func.min,
        "max": func.max,
    }
    return funcs.get(metric, func.sum)


async def _evaluate_trend(
    session: AsyncSession, page: Page, columns: list[PageColumn], config: TrendConfig
) -> WidgetEvaluationResponse:
    columns_by_key = {c.key: c for c in columns}
    expr, resolved_column = resolve_column(page, columns_by_key, config.column)
    model = model_for(page)
    since = date.today() - timedelta(days=config.days)
    bucket = func.date_trunc(config.bucket, model.business_date)  # type: ignore[attr-defined]

    stmt = (
        select(bucket.label("bucket"), _metric_func(config.metric)(expr))
        .select_from(model)
        .where(
            *base_conditions(page),
            model.business_date >= since,  # type: ignore[attr-defined]
            model.status == RecordStatus.ACTIVE,  # type: ignore[attr-defined]
        )
        .group_by(bucket)
        .order_by(bucket)
    )
    result = await session.execute(stmt)
    series = [
        TrendPoint(bucket=bucket_value.date(), value=_format_metric_value(value, resolved_column))
        for bucket_value, value in result
    ]
    return WidgetEvaluationResponse(widget_type="TREND", series=series)


async def evaluate_widget(
    session: AsyncSession, ctx: SecurityContext, widget: DashboardWidget
) -> WidgetEvaluationResponse:
    # The same double gate `list_widgets` applies — `GET .../data` takes a
    # widget id directly, so a manager who knows/guesses one can't reach a
    # widget `list_widgets` would have filtered out (a role-restricted
    # `visible_to`, or a page they can't view) just by calling this instead.
    if not ctx.is_owner and widget.visible_to is not None and widget.visible_to != ctx.role:
        raise NotFoundError("No such widget.")
    page = await get_for_company(session, Page, widget.page_id, ctx.company_id)  # type: ignore[arg-type]
    if page is None:
        raise NotFoundError("This widget's page no longer exists.")
    if not ctx.is_owner:
        await require_page_access(page.id, "view", ctx, session)
    columns = await page_service.get_page_columns(session, page.id)

    if widget.widget_type == "METRIC":
        metric_cfg = MetricConfig(**widget.config)
        current = await query_service.aggregate(
            session,
            page,
            columns,
            AggregateRequest(
                metric=metric_cfg.metric, column=metric_cfg.column, period=metric_cfg.period
            ),
        )
        comparison_value = None
        if metric_cfg.period == "current_month":
            comparison = await query_service.aggregate(
                session,
                page,
                columns,
                AggregateRequest(
                    metric=metric_cfg.metric, column=metric_cfg.column, period="last_month"
                ),
            )
            comparison_value = comparison.value
        return WidgetEvaluationResponse(
            widget_type="METRIC", value=current.value, comparison_value=comparison_value
        )

    if widget.widget_type == "TREND":
        return await _evaluate_trend(session, page, columns, TrendConfig(**widget.config))

    if widget.widget_type == "BREAKDOWN":
        breakdown_cfg = BreakdownConfig(**widget.config)
        result = await query_service.aggregate(
            session,
            page,
            columns,
            AggregateRequest(
                metric=breakdown_cfg.metric,
                column=breakdown_cfg.column,
                group_by=breakdown_cfg.group_by,
                period=breakdown_cfg.period,
            ),
        )
        groups = sorted(result.groups, key=lambda g: g.value, reverse=True)
        top = groups[: breakdown_cfg.top_n]
        return WidgetEvaluationResponse(widget_type="BREAKDOWN", groups=top)

    if widget.widget_type == "LIST":
        list_cfg = ListConfig(**widget.config)
        list_query = QueryRequest(
            filters=list_cfg.filters, sort=list_cfg.sort, limit=list_cfg.limit
        )
        page_result = await query_service.query_records(session, page, columns, list_query)
        return WidgetEvaluationResponse(
            widget_type="LIST", records=page_result.items, records_has_more=page_result.has_more
        )

    if widget.widget_type == "REVIEW_QUEUE":
        needs_review_filter = QueryFilter(column="needs_review", op="eq", value=True)
        page_result = await query_service.query_records(
            session,
            page,
            columns,
            QueryRequest(filters=[needs_review_filter], limit=50),
        )
        return WidgetEvaluationResponse(
            widget_type="REVIEW_QUEUE",
            records=page_result.items,
            records_has_more=page_result.has_more,
        )

    raise ValidationFailedError(f"Unknown widget_type: {widget.widget_type!r}.")


async def suggest_starter_widgets(
    session: AsyncSession, ctx: SecurityContext
) -> list[WidgetSuggestion]:
    """Never persisted (plan section 15.3) — synthesized fresh from whatever
    of the six system pages exist for this company. Only offered while the
    Owner hasn't already configured any widgets, so this never nags someone
    who has already built their own dashboard."""
    existing = await session.execute(
        select(func.count())
        .select_from(DashboardWidget)
        .where(DashboardWidget.company_id == ctx.company_id)
    )
    if existing.scalar_one() > 0:
        return []

    suggestions: list[WidgetSuggestion] = []
    if await page_service.get_page_by_key(session, ctx.company_id, "expenses") is not None:
        suggestions.append(
            WidgetSuggestion(
                title="This month's expenses",
                widget_type="METRIC",
                page_key="expenses",
                config={"metric": "sum", "column": "amount", "period": "current_month"},
            )
        )
    if await page_service.get_page_by_key(session, ctx.company_id, "daily_revenue") is not None:
        suggestions.append(
            WidgetSuggestion(
                title="Revenue by day",
                widget_type="TREND",
                page_key="daily_revenue",
                config={"column": "total_revenue", "metric": "sum", "bucket": "day", "days": 30},
            )
        )
    if await page_service.get_page_by_key(session, ctx.company_id, "cheques") is not None:
        suggestions.append(
            WidgetSuggestion(
                title="Pending cheques",
                widget_type="LIST",
                page_key="cheques",
                config={
                    "filters": [{"column": "cheque_status", "op": "eq", "value": "PENDING"}],
                    "sort": [{"column": "business_date", "direction": "asc"}],
                    "limit": 10,
                },
            )
        )
    if (
        await page_service.get_page_by_key(session, ctx.company_id, "daily_revenue") is not None
        and await page_service.get_page_by_key(session, ctx.company_id, "cash_ledger") is not None
    ):
        suggestions.append(
            WidgetSuggestion(
                title="Today's reconciliation",
                widget_type="METRIC",
                page_key="daily_revenue",
                config={"metric": "sum", "column": "total_revenue", "period": "current_month"},
            )
        )
    return suggestions


async def get_digest(
    session: AsyncSession, ctx: SecurityContext, digest_date: date | None
) -> DailyDigestOut | None:
    """Already company-scoped by RLS (`daily_digests`' own `tenant_isolation`
    policy, migration 0013) — no extra gate needed, unlike widgets/audit
    which have their own role/page-visibility rules on top of tenancy."""
    target_date = digest_date or date.today()
    result = await session.execute(
        select(DailyDigest).where(
            DailyDigest.company_id == ctx.company_id, DailyDigest.digest_date == target_date
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return DailyDigestOut(digest_date=row.digest_date, summary=row.summary)
