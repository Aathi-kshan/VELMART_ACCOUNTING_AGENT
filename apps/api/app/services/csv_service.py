"""CSV import and export — one generic pipeline for any page (plan section
13, P3.5 Part 2/3). Owner only, both directions.

Export deviates from docs/PROJECT_PLAN.md section 13.2 on purpose: the
locked spec writes the file to a bucket and returns a presigned URL, which
depends on `app/storage/` (confirmed empty, a P5 dependency). Export
instead returns the CSV directly as the response body — no bucket, no S3,
no presigned URL — and the Flutter client hands it to the OS share sheet.
Still true to the rest of section 13.2: UTF-8 with a BOM so Excel opens it
cleanly, and every export is audited as a data-egress event regardless of
delivery mechanism.

Import follows section 13.1's workflow — preview (encoding/delimiter/header
+ fuzzy-suggested mapping) -> validate (every row, against the page's live
schema, with natural-key duplicate detection) -> commit (chunked insert +
an `import_batches` row) -> optional rollback within 24 hours. There is no
server-side session for a partially-completed import: each step re-parses
the same file bytes the caller re-sends, since no cache/session
infrastructure exists yet and re-parsing a <=10MB CSV is cheap. `RECORD_REF`
columns are validated for shape only (a well-formed UUID) — matching
`record_service.py`'s own documented scope boundary — since resolving a
CSV cell's *display value* to a target row needs `reference_service.py`,
which doesn't exist until P4.
"""

from __future__ import annotations

import csv
import difflib
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.dates import DEFAULT_DAY_CUTOFF_HOUR, business_date_for, now_utc
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models.company import CompanySettings
from app.models.import_batch import ImportBatch
from app.models.page import Page
from app.models.page_column import ColumnType, PageColumn
from app.repositories.base import get_for_company
from app.repositories.records import (
    RecordHandle,
    base_conditions,
    create_row,
    generated_columns_for,
    model_for,
    soft_delete_by_import_batch,
    to_handle,
    to_wire_value,
    update_row,
)
from app.schemas.csv_import import (
    DateFormatHint,
    ImportBatchOut,
    ImportCommitResponse,
    ImportMappingRequest,
    ImportPreviewResponse,
    ImportRollbackResponse,
    ImportRowError,
    ImportValidateResponse,
)
from app.schemas.dynamic import build_record_model
from app.schemas.record import ExportRequest
from app.services.audit_service import write_audit_log
from app.services.query_service import apply_filters_and_search

_BOM = b"\xef\xbb\xbf"


def _cell(value: Any) -> str:
    """`None` -> empty cell; a `MULTI_SELECT` list -> `; `-joined; everything
    else is already wire-formatted (a money or number string, ISO date
    text) and needs no further conversion."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return str(value)


async def export_records_csv(
    session: AsyncSession, page: Page, columns: list[PageColumn], payload: ExportRequest
) -> tuple[bytes, int]:
    """Every row matching `payload.filters`/`payload.search`, oldest business
    date first. Returns the encoded CSV (BOM included) plus the row count,
    so the caller can audit the export without a second query to re-count."""
    model = model_for(page)
    stmt = select(model).where(*base_conditions(page))
    stmt = apply_filters_and_search(stmt, page, columns, payload.filters, payload.search)
    stmt = stmt.order_by(model.business_date)  # type: ignore[attr-defined]

    result = await session.execute(stmt)
    rows = result.scalars().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Business Date", *(column.name for column in columns)])
    for row in rows:
        handle = to_handle(row, page, columns)
        writer.writerow(
            [
                handle.business_date.isoformat(),
                *(_cell(handle.data.get(column.key)) for column in columns),
            ]
        )

    return _BOM + buffer.getvalue().encode("utf-8"), len(rows)


# ==========================================================================
# Import
# ==========================================================================

#: Section 13.1: "per-row error list" — capped so a CSV with thousands of
#: bad rows doesn't produce an unbounded response.
MAX_IMPORT_ERRORS = 200

#: Section 13.1: "chunked insert, 500 rows per transaction". The whole
#: import still commits as one request-scoped transaction (get_rls_session
#: owns it, same as every other write in this codebase — and section
#: 13.1's own rule, "a partial import that fails at row 4,000 is worse than
#: no import", argues for exactly that): this constant paces how many rows
#: go into one `session.flush()` batch, not where a COMMIT boundary falls.
IMPORT_CHUNK_SIZE = 500

_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "utf-8", "cp1252")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_SLASHED_DATE_RE = re.compile(r"^(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{1,4})$")


@dataclass
class ParsedCsv:
    encoding: str
    delimiter: str
    headers: list[str]
    rows: list[dict[str, str]]


@dataclass
class _PreparedRow:
    row_number: int
    validated: dict[str, Any]
    occurred_at: datetime
    business_date: date
    existing: RecordHandle | None


@dataclass
class _ImportRun:
    total_rows: int
    rows: list[_PreparedRow] = field(default_factory=list)
    errors: list[ImportRowError] = field(default_factory=list)
    errors_truncated: bool = False


def _decode_csv_bytes(raw: bytes) -> tuple[str, str]:
    """Best-effort encoding detection (section 13.1) without a new
    dependency: UTF-8 (BOM-aware) first — the overwhelmingly common case —
    then Windows-1252, the most likely alternative for a Sri Lankan
    business's Excel-exported CSV. The first that decodes cleanly wins."""
    for encoding in _ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValidationFailedError(
        "Could not read this file as text. Please export it as UTF-8 CSV and try again."
    )


def parse_csv(raw: bytes) -> ParsedCsv:
    text, encoding = _decode_csv_bytes(raw)
    if not text.strip():
        raise ValidationFailedError("This file is empty.")
    try:
        delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",;\t").delimiter
    except csv.Error:
        delimiter = ","

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = list(reader.fieldnames or [])
    rows = [{k: (v or "") for k, v in row.items() if k is not None} for row in reader]
    return ParsedCsv(encoding=encoding, delimiter=delimiter, headers=headers, rows=rows)


def _is_importable(column: PageColumn, generated: frozenset[str]) -> bool:
    if column.is_archived or column.key in generated:
        return False
    return column.data_type not in (ColumnType.FORMULA, ColumnType.ATTACHMENT)


def _best_match(header: str, candidates: dict[str, str], used: set[str]) -> str | None:
    names = [name for name, key in candidates.items() if key not in used]
    exact = {name.lower(): name for name in names}.get(header.strip().lower())
    if exact:
        return candidates[exact]
    close = difflib.get_close_matches(header.strip(), names, n=1, cutoff=0.6)
    return candidates[close[0]] if close else None


def suggest_mapping(
    headers: list[str], columns: list[PageColumn], generated: frozenset[str]
) -> dict[str, str | None]:
    candidates = {c.name: c.key for c in columns if _is_importable(c, generated)}
    used: set[str] = set()
    suggestion: dict[str, str | None] = {}
    for header in headers:
        key = _best_match(header, candidates, used)
        if key:
            used.add(key)
        suggestion[header] = key
    return suggestion


async def preview_import(
    raw: bytes, page: Page, columns: list[PageColumn]
) -> ImportPreviewResponse:
    parsed = parse_csv(raw)
    generated = generated_columns_for(page)
    mapping = suggest_mapping(parsed.headers, columns, generated)
    return ImportPreviewResponse(
        encoding=parsed.encoding,
        delimiter=parsed.delimiter,
        headers=parsed.headers,
        suggested_mapping=mapping,
        row_count=len(parsed.rows),
        sample_rows=parsed.rows[:5],
    )


def normalize_money_cell(raw: str) -> str:
    """Section 13.1: strip `Rs.`, strip thousands separators, treat
    `(1,234.00)` as negative."""
    text = raw.strip()
    if not text:
        return text
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    text = re.sub(r"(?i)^rs\.?\s*", "", text)
    text = text.replace(",", "").strip()
    if text.startswith("-"):
        negative = True
        text = text[1:]
    return f"-{text}" if negative else text


def normalize_temporal_cell(
    raw: str, hint: DateFormatHint | None, *, is_datetime: bool
) -> tuple[str | None, str | None]:
    """Returns `(normalized_iso_value, error_message)` — exactly one is
    non-`None`. Unambiguous ISO text passes straight through; a slash/dash
    numeric date needs `hint` to disambiguate DMY/MDY/YMD (section 13.1:
    "ambiguous dates prompt the Owner to confirm the format. Never
    guess."); anything else is left for the normal per-column validator to
    accept or reject on its own terms."""
    text = raw.strip()
    if not text:
        return None, None

    if "T" in text:
        date_part, _, time_part = text.partition("T")
    elif " " in text:
        date_part, _, time_part = text.partition(" ")
    else:
        date_part, time_part = text, ""

    if _ISO_DATE_RE.match(date_part):
        normalized_date = date_part[:10]
    else:
        match = _SLASHED_DATE_RE.match(date_part)
        if not match:
            return text, None
        if hint is None:
            return (
                None,
                "Ambiguous date format — set a date format (DMY/MDY/YMD) "
                "for this column before importing.",
            )
        a, b, c = match.groups()
        if hint == "YMD":
            year_s, month_s, day_s = a, b, c
        elif hint == "DMY":
            day_s, month_s, year_s = a, b, c
        else:
            month_s, day_s, year_s = a, b, c
        try:
            year_i, month_i, day_i = int(year_s), int(month_s), int(day_s)
            if len(year_s) == 2:
                year_i += 2000
            date(year_i, month_i, day_i)
        except ValueError:
            return None, f"{raw!r} is not a valid date under the {hint} format."
        normalized_date = f"{year_i:04d}-{month_i:02d}-{day_i:02d}"

    if not is_datetime:
        return normalized_date, None
    return (f"{normalized_date}T{time_part}" if time_part else f"{normalized_date}T00:00:00", None)


async def _derive_import_dates(
    session: AsyncSession, ctx: SecurityContext, page: Page, validated: dict[str, Any]
) -> tuple[datetime, date]:
    value = validated.get(page.date_column_key) if page.date_column_key else None
    if isinstance(value, datetime):
        occurred_at = value if value.tzinfo else value.replace(tzinfo=UTC)
        return occurred_at, occurred_at.date()
    if isinstance(value, date):
        occurred_at = datetime.combine(value, time.min, tzinfo=UTC)
        return occurred_at, value

    settings = await session.get(CompanySettings, ctx.company_id)
    cutoff = settings.day_cutoff_hour if settings else DEFAULT_DAY_CUTOFF_HOUR
    occurred_at = now_utc()
    return occurred_at, business_date_for(occurred_at, cutoff_hour=cutoff)


async def _load_existing_natural_keys(
    session: AsyncSession, page: Page, columns: list[PageColumn], natural_key_columns: list[str]
) -> dict[tuple[Any, ...], RecordHandle]:
    if not natural_key_columns:
        return {}
    model = model_for(page)
    result = await session.execute(select(model).where(*base_conditions(page)))
    existing: dict[tuple[Any, ...], RecordHandle] = {}
    for row in result.scalars().all():
        handle = to_handle(row, page, columns)
        existing[tuple(handle.data.get(k) for k in natural_key_columns)] = handle
    return existing


async def _run_import(
    session: AsyncSession,
    ctx: SecurityContext,
    page: Page,
    columns: list[PageColumn],
    raw: bytes,
    payload: ImportMappingRequest,
) -> _ImportRun:
    parsed = parse_csv(raw)
    columns_by_key = {c.key: c for c in columns}
    generated = generated_columns_for(page)
    importable_keys = {c.key for c in columns if _is_importable(c, generated)}

    mapped_keys = list(payload.mapping.values())
    for key in mapped_keys:
        if key not in importable_keys:
            raise ValidationFailedError(
                f"{key!r} cannot be imported into (unknown, read-only, or generated)."
            )
    if len(mapped_keys) != len(set(mapped_keys)):
        raise ValidationFailedError("Two CSV headers cannot map to the same column.")
    for key in payload.natural_key_columns:
        if key not in importable_keys:
            raise ValidationFailedError(f"{key!r} is not a valid column on this page.")

    model_cls = build_record_model(columns, readonly_extra=generated)
    existing_by_key = await _load_existing_natural_keys(
        session, page, columns, payload.natural_key_columns
    )

    errors: list[ImportRowError] = []
    prepared: list[_PreparedRow] = []

    for index, raw_row in enumerate(parsed.rows, start=1):
        row_errors: list[ImportRowError] = []
        cells: dict[str, Any] = {}

        for header, key in payload.mapping.items():
            cell = raw_row.get(header, "").strip()
            if not cell:
                continue
            column = columns_by_key[key]
            if column.data_type is ColumnType.CURRENCY:
                cells[key] = normalize_money_cell(cell)
            elif column.data_type in (ColumnType.DATE, ColumnType.DATETIME):
                normalized, err = normalize_temporal_cell(
                    cell,
                    payload.date_formats.get(key),
                    is_datetime=column.data_type is ColumnType.DATETIME,
                )
                if err:
                    row_errors.append(ImportRowError(row=index, column=column.name, message=err))
                    continue
                cells[key] = normalized
            elif column.data_type is ColumnType.MULTI_SELECT:
                cells[key] = [v.strip() for v in cell.split(";") if v.strip()]
            elif column.data_type is ColumnType.BOOLEAN:
                cells[key] = cell.lower() in ("true", "yes", "1", "y")
            else:
                cells[key] = cell

        if row_errors:
            errors.extend(row_errors)
            continue

        try:
            validated = model_cls(**cells).model_dump()
        except ValidationError as exc:
            for e in exc.errors(include_url=False, include_context=False):
                col_key = e["loc"][0] if e["loc"] else None
                col_name = (
                    columns_by_key[col_key].name if col_key in columns_by_key else str(col_key)
                )
                errors.append(ImportRowError(row=index, column=col_name, message=e["msg"]))
            continue

        occurred_at, business_date = await _derive_import_dates(session, ctx, page, validated)

        existing = None
        if payload.natural_key_columns:
            wire_key = tuple(
                to_wire_value(columns_by_key[k], validated.get(k))
                for k in payload.natural_key_columns
            )
            existing = existing_by_key.get(wire_key)

        prepared.append(
            _PreparedRow(
                row_number=index,
                validated=validated,
                occurred_at=occurred_at,
                business_date=business_date,
                existing=existing,
            )
        )

    return _ImportRun(
        total_rows=len(parsed.rows),
        rows=prepared,
        errors=errors[:MAX_IMPORT_ERRORS],
        errors_truncated=len(errors) > MAX_IMPORT_ERRORS,
    )


async def validate_import(
    session: AsyncSession,
    ctx: SecurityContext,
    page: Page,
    columns: list[PageColumn],
    raw: bytes,
    payload: ImportMappingRequest,
) -> ImportValidateResponse:
    run = await _run_import(session, ctx, page, columns, raw, payload)
    duplicate_rows = sum(1 for r in run.rows if r.existing is not None)
    return ImportValidateResponse(
        total_rows=run.total_rows,
        valid_rows=len(run.rows),
        duplicate_rows=duplicate_rows,
        error_rows=len(run.errors),
        errors=run.errors,
        errors_truncated=run.errors_truncated,
    )


async def commit_import(
    session: AsyncSession,
    ctx: SecurityContext,
    page: Page,
    columns: list[PageColumn],
    raw: bytes,
    payload: ImportMappingRequest,
    file_name: str,
) -> ImportCommitResponse:
    """Re-validates from scratch (never trusts that a prior `/validate` call
    still reflects reality) and writes every row that isn't skipped, in one
    request-scoped transaction — see `IMPORT_CHUNK_SIZE`'s docstring for why
    that's one commit, not several."""
    run = await _run_import(session, ctx, page, columns, raw, payload)

    batch = ImportBatch(
        company_id=ctx.company_id,
        page_id=page.id,
        file_name=file_name,
        mapping=payload.mapping,
        total_rows=run.total_rows,
        created_by=ctx.user_id,
    )
    session.add(batch)
    await session.flush()  # assigns batch.id

    imported = 0
    skipped = 0
    for chunk_start in range(0, len(run.rows), IMPORT_CHUNK_SIZE):
        for prepared_row in run.rows[chunk_start : chunk_start + IMPORT_CHUNK_SIZE]:
            if prepared_row.existing is not None:
                if payload.duplicate_strategy == "skip":
                    skipped += 1
                    continue
                if payload.duplicate_strategy == "update":
                    await update_row(
                        session,
                        page,
                        prepared_row.existing,
                        columns,
                        validated=prepared_row.validated,
                        occurred_at=prepared_row.occurred_at,
                        store_id=None,
                        business_date=prepared_row.business_date,
                        updated_by=ctx.user_id,
                    )
                    imported += 1
                    continue
                # "create_anyway" falls through to a fresh insert below.
            await create_row(
                session,
                page,
                columns,
                company_id=ctx.company_id,
                store_id=None,
                occurred_at=prepared_row.occurred_at,
                business_date=prepared_row.business_date,
                validated=prepared_row.validated,
                created_by=ctx.user_id,
                client_uuid=None,
                source="CSV",
                import_batch_id=batch.id,
            )
            imported += 1
        await session.flush()

    await session.execute(
        update(ImportBatch)
        .where(ImportBatch.id == batch.id)
        .values(imported_rows=imported, skipped_rows=skipped, status="COMMITTED")
    )

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="CSV_IMPORT",
        entity_type="import_batch",
        entity_id=batch.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        new_data={
            "page_id": str(page.id),
            "total_rows": run.total_rows,
            "imported_rows": imported,
            "skipped_rows": skipped,
            "error_rows": len(run.errors),
        },
    )

    return ImportCommitResponse(
        batch_id=batch.id,
        total_rows=run.total_rows,
        imported_rows=imported,
        skipped_rows=skipped,
        error_rows=len(run.errors),
    )


def _can_rollback(batch: ImportBatch) -> bool:
    return batch.status == "COMMITTED" and (now_utc() - batch.created_at) <= timedelta(hours=24)


async def list_import_batches(
    session: AsyncSession, ctx: SecurityContext, page_id: uuid.UUID
) -> list[ImportBatchOut]:
    result = await session.execute(
        select(ImportBatch)
        .where(ImportBatch.company_id == ctx.company_id, ImportBatch.page_id == page_id)
        .order_by(ImportBatch.created_at.desc())
        .limit(20)
    )
    return [
        ImportBatchOut(
            id=batch.id,
            page_id=batch.page_id,
            file_name=batch.file_name,
            total_rows=batch.total_rows,
            imported_rows=batch.imported_rows,
            skipped_rows=batch.skipped_rows,
            status=batch.status,
            created_at=batch.created_at,
            can_rollback=_can_rollback(batch),
        )
        for batch in result.scalars().all()
    ]


async def rollback_import(
    session: AsyncSession, ctx: SecurityContext, batch_id: uuid.UUID
) -> ImportRollbackResponse:
    batch = await get_for_company(session, ImportBatch, batch_id, ctx.company_id)
    if batch is None:
        raise NotFoundError("No such import batch.")
    if batch.status == "ROLLED_BACK":
        raise ConflictError("This import has already been rolled back.")
    if not _can_rollback(batch):
        raise ConflictError(
            "This import is more than 24 hours old and can no longer be rolled back."
        )

    page = await get_for_company(session, Page, batch.page_id, ctx.company_id)
    assert page is not None  # a batch's own page_id always resolves in-company

    rolled_back = await soft_delete_by_import_batch(
        session,
        page,
        import_batch_id=batch.id,
        reason="CSV import rollback",
        updated_by=ctx.user_id,
    )

    await session.execute(
        update(ImportBatch).where(ImportBatch.id == batch.id).values(status="ROLLED_BACK")
    )

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="CSV_IMPORT_ROLLBACK",
        entity_type="import_batch",
        entity_id=batch.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        old_data={"rolled_back_rows": rolled_back},
    )

    return ImportRollbackResponse(batch_id=batch.id, rolled_back_rows=rolled_back)
