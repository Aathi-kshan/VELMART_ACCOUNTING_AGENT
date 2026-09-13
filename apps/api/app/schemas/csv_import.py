"""Request/response shapes for CSV import (plan section 13.1) — one generic
pipeline for any page: upload -> preview (encoding/delimiter/header +
suggested mapping) -> validate (every row, against the live schema, with
natural-key dedup) -> commit (chunked insert + `import_batches` row) ->
optional rollback within 24 hours.

Owner only, same as export. Every step re-sends the file: there is no
server-side session/cache for a partially-completed import (no such
infrastructure exists yet, and re-parsing a <=10MB CSV is cheap), so the
client holds the picked file in memory across the wizard's steps.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

#: How to read an ambiguous (slash-separated) date/datetime column — the
#: Owner sets this once per column, not per cell (plan section 13.1:
#: "ambiguous dates prompt the Owner to confirm the format. Never guess.").
#: Unambiguous ISO text (`2026-09-01`) is always accepted regardless of this.
DateFormatHint = Literal["YMD", "DMY", "MDY"]

DuplicateStrategy = Literal["skip", "update", "create_anyway"]


class ImportRowError(BaseModel):
    #: 1-indexed data row (the header doesn't count as row 1).
    row: int
    column: str | None = None
    message: str


class ImportPreviewResponse(BaseModel):
    encoding: str
    delimiter: str
    headers: list[str]
    #: CSV header -> this page's column `key`, fuzzy-matched by name; `null`
    #: for a header with no confident match. FORMULA/ATTACHMENT columns and
    #: this page's generated columns are never suggested — nothing can be
    #: imported into them (plan section 3.5.8 / 13.1).
    suggested_mapping: dict[str, str | None]
    row_count: int
    #: First few rows, raw (pre-validation) cell text, for the Owner to
    #: sanity-check the mapping against real data before confirming it.
    sample_rows: list[dict[str, str]]


class ImportMappingRequest(BaseModel):
    """The shared body for `/validate` and `/commit` — the Owner's confirmed
    mapping plus how to handle duplicates and ambiguous dates."""

    #: CSV header -> column key. A header omitted here is simply not
    #: imported (its data is dropped, same as an unmapped column always
    #: would be).
    mapping: dict[str, str] = Field(default_factory=dict)
    #: Column keys whose combined value identifies "the same row" across an
    #: import and the page's existing data (e.g. Date + Cheque Number).
    #: Empty means every row is a new row (`duplicate_strategy` has nothing
    #: to act on).
    natural_key_columns: list[str] = Field(default_factory=list)
    duplicate_strategy: DuplicateStrategy = "create_anyway"
    date_formats: dict[str, DateFormatHint] = Field(default_factory=dict)


class ImportValidateResponse(BaseModel):
    total_rows: int
    valid_rows: int
    #: Rows that matched an existing natural key under `duplicate_strategy
    #: == "skip"` — counted separately from `error_rows` since these aren't
    #: wrong, just already present.
    duplicate_rows: int
    error_rows: int
    errors: list[ImportRowError]
    #: True when `errors` was capped (plan section 13.1's "per-row error
    #: list" — capped here at `MAX_IMPORT_ERRORS` rather than an unbounded
    #: response for a CSV with thousands of bad rows).
    errors_truncated: bool


class ImportCommitResponse(BaseModel):
    batch_id: uuid.UUID
    total_rows: int
    imported_rows: int
    skipped_rows: int
    error_rows: int


class ImportBatchOut(BaseModel):
    id: uuid.UUID
    page_id: uuid.UUID
    file_name: str
    total_rows: int
    imported_rows: int
    skipped_rows: int
    status: str
    created_at: datetime
    #: Computed server-side: `status == "COMMITTED"` and within 24 hours of
    #: `created_at` (plan section 13.1).
    can_rollback: bool


class ImportRollbackResponse(BaseModel):
    batch_id: uuid.UUID
    rolled_back_rows: int
