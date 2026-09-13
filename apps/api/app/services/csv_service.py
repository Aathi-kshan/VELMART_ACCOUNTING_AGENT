"""CSV export — one generic pipeline for any page (plan section 13.2, P3.5
Part 2). Owner only.

Deviates from docs/PROJECT_PLAN.md section 13.2 on purpose: the locked spec
writes the file to a bucket and returns a presigned URL, which depends on
`app/storage/` (confirmed empty, a P5 dependency). Export instead returns
the CSV directly as the response body — no bucket, no S3, no presigned URL
— and the Flutter client hands it to the OS share sheet. Still true to the
rest of section 13.2: UTF-8 with a BOM so Excel opens it cleanly, and every
export is audited as a data-egress event (`app/routers/exports.py`)
regardless of delivery mechanism.

CSV import was a separate feature and has been removed entirely (product
decision) — this file, and this docstring, cover export only now.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.page import Page
from app.models.page_column import PageColumn
from app.repositories.records import base_conditions, model_for, to_handle
from app.schemas.record import ExportRequest
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

