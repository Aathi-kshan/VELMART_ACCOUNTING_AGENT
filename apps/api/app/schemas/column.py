"""Request/response shapes for column management (plan sections 8.3, 10.2,
10.3, 21.2; docs/API.md §4).
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.page_column import ColumnType


class ColumnDefinition(BaseModel):
    """One column inside `POST /pages` or the body of `POST /pages/{id}/columns`.

    `key` is never accepted here — it's always derived server-side from
    `name` (plan section 10.3: "Change key — Not allowed. Would orphan every
    existing value").
    """

    name: str = Field(min_length=1, max_length=200)
    data_type: ColumnType
    is_required: bool = False
    is_indexed: bool = False
    is_protected: bool = False
    config: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None


class ColumnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    page_id: uuid.UUID
    key: str
    name: str
    data_type: ColumnType
    position: int
    is_required: bool
    is_indexed: bool
    is_protected: bool
    config: dict[str, Any]
    description: str | None
    is_archived: bool


class UpdateColumnRequest(BaseModel):
    """Every field optional: a PATCH only touches what it sends.

    Narrowing `data_type` (e.g. TEXT -> NUMBER) requires `confirm_narrow`
    (plan section 10.3) — call `POST /columns/{id}/narrow-dry-run` first to
    see how many existing rows would fail; narrowing never mutates or
    deletes those rows, it only tightens validation for future writes.
    """

    #: Never actually changeable — present only so a client that tries gets
    #: an explicit 409 `COLUMN_KEY_IMMUTABLE` rather than a silently ignored
    #: field (docs/API.md §4).
    key: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    data_type: ColumnType | None = None
    confirm_narrow: bool = False
    position: int | None = None
    is_required: bool | None = None
    is_indexed: bool | None = None
    is_protected: bool | None = None
    config: dict[str, Any] | None = None
    description: str | None = None
    is_archived: bool | None = None


class UpdateColumnResponse(ColumnOut):
    #: Populated only when an update removes SELECT/MULTI_SELECT options
    #: that existing records still use (plan section 10.3: warn, don't
    #: block).
    removed_options_in_use: dict[str, int] = Field(default_factory=dict)


class NarrowDryRunResult(BaseModel):
    would_fail: int
    sample_failures: list[dict[str, Any]] = Field(default_factory=list)


class NarrowDryRunRequest(BaseModel):
    data_type: ColumnType
