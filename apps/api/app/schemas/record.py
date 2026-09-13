"""Request/response shapes for records, query, and aggregate (plan sections
9.1, 10.4, 21.2; docs/API.md §5).

`CreateRecordRequest.data`/`UpdateRecordRequest.data` are deliberately plain
`dict[str, Any]` here — the *real* validation is the page-specific model
`app/schemas/dynamic.py` builds from that page's live columns, which this
generic request shape can't know about. `RecordOut.data` is likewise passed
through as stored: every value already lives in `records.data` in wire
format (money as a string, dates as ISO text — plan section 9.1), so no
re-serialization happens on the way out.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.base import RecordStatus
from app.schemas.common import QueryFilter, SortSpec


class CreateRecordRequest(BaseModel):
    occurred_at: datetime
    client_uuid: uuid.UUID | None = None
    store_id: uuid.UUID | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class UpdateRecordRequest(BaseModel):
    #: Optimistic-locking version, as an alternative to the `If-Match` header
    #: (docs/API.md §1.2) — either is accepted; the router resolves which one
    #: was actually supplied.
    version: int | None = None
    occurred_at: datetime | None = None
    store_id: uuid.UUID | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class DeleteRecordRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class SetProtectedFieldRequest(BaseModel):
    """docs/API.md §5 / plan section 11.4 — the only body a protected
    column ever accepts: which column, its new value, and the version
    being changed from (optimistic locking, same as any other update).
    `column_key` matches docs/API.md's documented field name exactly (a P4
    fix — the field was originally shipped as `column`)."""

    column_key: str
    value: str
    version: int | None = None


class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    #: Set only on a reversal's replacement record (P4 §8) — always `None`
    #: on a native/system-table row, and on every ordinary record.
    reverses_id: uuid.UUID | None = None


class ReverseRecordRequest(BaseModel):
    """`POST /records/{id}/reverse` (plan section 11.5, P4 §8) — `kind=LEDGER`
    pages only. `version` is the *original* record's optimistic-locking
    version. Omitting `data` means "void this record, nothing replaces it";
    supplying it creates a new `ACTIVE` record linked via `reverses_id`,
    validated/formula-computed exactly like an ordinary create
    (`record_service.create_record`'s own pipeline, not a parallel one)."""

    version: int
    data: dict[str, Any] | None = None
    occurred_at: datetime | None = None
    store_id: uuid.UUID | None = None


class ReverseRecordResponse(BaseModel):
    original: RecordOut
    replacement: RecordOut | None = None


class RunningBalanceEntry(BaseModel):
    record_id: uuid.UUID
    business_date: date
    #: The balance column's own value on this row (wire format, a money
    #: string) — alongside the cumulative total, so a client can render both
    #: without a second round trip.
    amount: str
    balance: str


class RunningBalanceResponse(BaseModel):
    entries: list[RunningBalanceEntry] = Field(default_factory=list)


class ExportRequest(BaseModel):
    """`POST /pages/{id}/export` (plan section 13.2 / P3.5 Part 2). Deliberately
    a subset of `QueryRequest`'s fields: an export has no `cursor`/`limit`
    (every matching row goes out) and no client-chosen `sort` (rows are
    always written in `business_date` order)."""

    filters: list[QueryFilter] = Field(default_factory=list)
    search: str | None = None


class QueryRequest(BaseModel):
    filters: list[QueryFilter] = Field(default_factory=list)
    search: str | None = None
    sort: list[SortSpec] = Field(default_factory=list)
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


#: docs/API.md §5: sum, avg, count, min, max.
AggregateMetric = Literal["sum", "avg", "count", "min", "max"]
#: Server-resolved relative windows over `business_date` — kept small and
#: explicit rather than accepting arbitrary date math from the client.
AggregatePeriod = Literal["current_month", "last_month", "current_year", "all_time"]


class AggregateRequest(BaseModel):
    metric: AggregateMetric
    #: Required for every metric except `count`, which may count whole rows.
    column: str | None = None
    group_by: str | None = None
    period: AggregatePeriod = "all_time"
    filters: list[QueryFilter] = Field(default_factory=list)


class AggregateGroup(BaseModel):
    key: str
    value: str
    count: int


class AggregatePeriodRange(BaseModel):
    from_: date | None = Field(default=None, alias="from")
    to: date | None = None

    model_config = ConfigDict(populate_by_name=True)


class AggregateResponse(BaseModel):
    value: str
    record_count: int
    period: AggregatePeriodRange
    groups: list[AggregateGroup] = Field(default_factory=list)


class ColumnValuesResponse(BaseModel):
    values: list[str]
