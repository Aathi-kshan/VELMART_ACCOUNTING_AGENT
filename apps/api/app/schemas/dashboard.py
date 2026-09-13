"""Dashboard: `GET /reconciliation` (docs/API.md §1.8, P3.5) and configurable
widgets (plan section 15, P5).

A widget's `config` embeds the *same* filter/sort/aggregate shapes
`app/schemas/record.py` already defines (`QueryFilter`, `SortSpec`,
`AggregateMetric`, `AggregatePeriod`) rather than a second, parallel query
language — evaluation (`app/services/dashboard_service.py`) reuses
`query_service.py`'s `aggregate`/`query_records` directly for every widget
type except `TREND`, which needs day-bucketing neither of those has today.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.user import UserRole
from app.schemas.common import QueryFilter, SortSpec
from app.schemas.record import AggregateGroup, AggregateMetric, AggregatePeriod, RecordOut


class ReconciliationItem(BaseModel):
    business_date: date
    revenue_total: str
    ledger_total: str
    difference: str


class ReconciliationResponse(BaseModel):
    items: list[ReconciliationItem]


class WidgetUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    config: dict[str, Any] | None = None
    position: int | None = None
    visible_to: UserRole | None = None
    #: `visible_to=None` in the request body is indistinguishable from "not
    #: sent" once Pydantic parses it — this is the explicit "reset to
    #: everyone" signal, the same `exclude_unset`-adjacent problem
    #: `UpdateColumnRequest`'s own fields don't have to solve since none of
    #: them are ever meant to go back to `None`.
    clear_visible_to: bool = False


class WidgetOut(BaseModel):
    id: uuid.UUID
    title: str
    widget_type: str
    page_id: uuid.UUID | None
    config: dict[str, Any]
    position: int
    visible_to: UserRole | None
    created_at: datetime


class TrendPoint(BaseModel):
    bucket: date
    value: str


class WidgetEvaluationResponse(BaseModel):
    """One shape for every widget type — only the field(s) matching
    `widget_type` are populated, the rest stay `None`. Simplest for the
    Flutter client to switch on (`switch (widgetType) { ... }`) without a
    union/discriminated-type dance for what is, in practice, always exactly
    one caller reading exactly one field."""

    widget_type: str
    #: METRIC
    value: str | None = None
    comparison_value: str | None = None
    #: TREND
    series: list[TrendPoint] | None = None
    #: BREAKDOWN
    groups: list[AggregateGroup] | None = None
    #: LIST / REVIEW_QUEUE
    records: list[RecordOut] | None = None
    records_has_more: bool | None = None


class MetricConfig(BaseModel):
    metric: AggregateMetric
    column: str | None = None
    period: AggregatePeriod = "all_time"


class TrendConfig(BaseModel):
    column: str
    metric: AggregateMetric = "sum"
    bucket: Literal["day", "week"] = "day"
    days: int = Field(default=30, ge=1, le=365)


class BreakdownConfig(BaseModel):
    group_by: str
    metric: AggregateMetric
    column: str | None = None
    period: AggregatePeriod = "all_time"
    top_n: int = Field(default=5, ge=1, le=20)


class ListConfig(BaseModel):
    filters: list[QueryFilter] = Field(default_factory=list)
    sort: list[SortSpec] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=50)


class DailyDigestOut(BaseModel):
    """`GET /dashboard/digest` (P5 §nightly-ops) — the structured summary
    `app/tasks/daily_digest.py` writes once per company per day. `summary`'s
    keys are the lowercased tracked audit actions plus `needs_review_count`
    — see that task's own `_TRACKED_ACTIONS`."""

    digest_date: date
    summary: dict[str, Any]
