"""`RECORD_REF` resolution and integrity (plan section 11.2, P4 §5).

A `RECORD_REF` column points at another page's row, named by that page's
*key*, not its id — `page_column.config['target_page_key']`
(`page_service.validate_column_config` already enforces this names a real,
non-archived page at column-save time; `display_column`, if given, is
already validated to be a real column on that page). This module is what
enforces a `RECORD_REF` *value* still points at a real, non-deleted row on
every record write, and what blocks deleting a row anything still points
at — never creating a stub for a missing target, per the locked spec.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.errors import ReferencedRecordExistsError, ReferenceNotFoundError
from app.models.page import Page
from app.models.page_column import ColumnType, PageColumn
from app.repositories.records import base_conditions, get_row, model_for, resolve_column
from app.services import page_service


async def _resolve_target_page(
    session: AsyncSession, ctx: SecurityContext, target_page_key: str, cache: dict[str, Page]
) -> Page:
    """Cached within one validation call — a page can have several
    `RECORD_REF` columns pointing at the same target."""
    cached = cache.get(target_page_key)
    if cached is not None:
        return cached
    page = await page_service.get_page_by_key(session, ctx.company_id, target_page_key)
    if page is None:
        # Config validation already guarantees this at save time — a target
        # page vanishing between then and now (deleted key reused elsewhere
        # is impossible; keys are never freed) would mean corrupt config,
        # not a real record's fault. Treated the same as "no such record"
        # rather than a 500, since either way the value can't be resolved.
        raise ReferenceNotFoundError(f"'{target_page_key}' is not a real page in this company.")
    cache[target_page_key] = page
    return page


async def validate_record_refs(
    session: AsyncSession,
    ctx: SecurityContext,
    columns: list[PageColumn],
    validated: dict[str, Any],
) -> None:
    """Existence check for every `RECORD_REF` value present in `validated`.

    A target in the wrong page and a target in another company are rejected
    identically — `get_row` is already scoped to (this company, that exact
    target page), so a record that exists but doesn't match both conditions
    is indistinguishable from one that doesn't exist at all, never leaking
    which."""
    page_cache: dict[str, Page] = {}
    columns_cache: dict[str, list[PageColumn]] = {}

    for column in columns:
        if column.data_type is not ColumnType.RECORD_REF:
            continue
        value = validated.get(column.key)
        if value is None:
            continue

        # `page_service.validate_column_config` already guarantees this is a
        # non-empty string at column-save time.
        target_page_key = str(column.config.get("target_page_key"))
        target_page = await _resolve_target_page(session, ctx, target_page_key, page_cache)
        target_columns = columns_cache.get(target_page.key)
        if target_columns is None:
            target_columns = await page_service.get_page_columns(session, target_page.id)
            columns_cache[target_page.key] = target_columns

        record_id = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        row = await get_row(session, target_page, target_columns, record_id, ctx.company_id)
        if row is None or row.is_deleted:
            raise ReferenceNotFoundError(f"{column.name}: no such record on '{target_page.name}'.")


async def check_no_inbound_references(
    session: AsyncSession, ctx: SecurityContext, page: Page, record_id: uuid.UUID
) -> None:
    """Called before soft-deleting a record: does any *other* page's
    `RECORD_REF` column still point at it? A metadata-driven scan across
    every page in the company — bounded by page count and each page's own
    row count, reasonable at this project's scale (plan section 11.2); if it
    ever becomes a hot path, indexing `RECORD_REF` columns is the natural
    next lever, not a redesign."""
    result = await session.execute(
        select(PageColumn, Page)
        .join(Page, Page.id == PageColumn.page_id)
        .where(
            Page.company_id == ctx.company_id,
            PageColumn.data_type == ColumnType.RECORD_REF,
            PageColumn.is_archived.is_(False),
            PageColumn.config["target_page_key"].astext == page.key,
        )
    )
    referencing_columns: list[tuple[PageColumn, Page]] = list(result.all())  # type: ignore[arg-type]

    for ref_column, ref_page in referencing_columns:
        ref_columns = await page_service.get_page_columns(session, ref_page.id)
        columns_by_key = {c.key: c for c in ref_columns}
        expr, _ = resolve_column(ref_page, columns_by_key, ref_column.key)
        # A generic page stores `RECORD_REF` as wire-format text in JSONB
        # (`to_wire_value`); a native page's own real column, if it ever has
        # one, holds a typed UUID directly — matching each backend's actual
        # storage shape rather than one guessed comparison type for both.
        compare_value: Any = record_id if ref_page.storage_table else str(record_id)
        count_result = await session.execute(
            select(func.count())
            .select_from(model_for(ref_page))
            .where(*base_conditions(ref_page), expr == compare_value)
        )
        count = count_result.scalar_one()
        if count:
            raise ReferencedRecordExistsError(
                f"{count} record(s) on '{ref_page.name}' still reference this record.",
                extra={"page": ref_page.key, "count": count},
            )
