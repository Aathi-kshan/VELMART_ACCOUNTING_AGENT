"""Shared shapes for list endpoints (plan sections 10.4, 21.1, docs/API.md §1.3).

`Paginated` is the cursor-paginated envelope every list endpoint returns.
`QueryFilter`/`SortSpec` are the structured filter/sort language shared by
`POST /pages/{id}/records/query` and (later) CSV export / AI tool calls —
declared once here rather than duplicated per caller.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

#: docs/API.md §5: "eq, neq, gt, gte, lt, lte, between, in, contains, is_null".
FilterOp = Literal["eq", "neq", "gt", "gte", "lt", "lte", "between", "in", "contains", "is_null"]


class QueryFilter(BaseModel):
    column: str
    op: FilterOp
    #: Absent/None for `is_null`; a 2-element list for `between`; a list for
    #: `in`; a single scalar otherwise. Shape is checked once the column's
    #: real type is known (app/services/query_service.py), not here — this
    #: model only carries the request across the wire.
    value: Any = None


class SortSpec(BaseModel):
    column: str
    direction: Literal["asc", "desc"] = "asc"


class Paginated[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False


DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 500


class PageQueryParams(BaseModel):
    """Query-string params for a plain (non-filtered) list — GET endpoints."""

    cursor: str | None = None
    limit: int = Field(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
