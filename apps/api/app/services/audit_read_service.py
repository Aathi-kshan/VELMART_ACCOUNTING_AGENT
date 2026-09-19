"""Audit log read path (plan section 18.3, P5) — the Owner-facing view.

Deliberately separate from `audit_service.py` (the append-only writer): this
module never writes a row, only filters/formats what's already there. The
writer stays exactly what it was before this phase — a single, trusted,
minimal INSERT path — with no read-path complexity mixed in.
"""

from __future__ import annotations

import csv
import io
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.models.audit import AuditLog
from app.repositories.audit import AuditLogRow, list_audit_logs
from app.schemas.audit import AuditLogEntry, AuditLogPage, AuditLogQuery
from app.services import page_service

#: UTF-8 with a BOM so Excel opens it correctly (same convention as
#: `csv_service.py`'s page-record export).
_BOM = b"\xef\xbb\xbf"


def _diff_fields(
    old_data: dict | None, new_data: dict | None
) -> list[tuple[str, object, object]]:
    """The `diff` column on `audit_logs` is never written to (P4/P5 research
    found nothing populates it) — a diff is cheaper to compute here, on the
    two JSONB blobs already stored, than to also maintain at write time."""
    if not old_data or not new_data:
        return []
    return [
        (key, old_data[key], new_data[key])
        for key in new_data
        if key in old_data and old_data[key] != new_data[key]
    ]


def format_sentence(entry: AuditLog, actor_name: str | None, page_name: str | None) -> str:
    """One sentence per `action`, matching the exact examples in
    docs/PROJECT_PLAN.md §18.3. Covers every action string actually used in
    this codebase (kept in sync with `AuditAction`, `app/models/audit.py`)
    plus a generic fallback so an unmatched future action never crashes
    this — it just reads a little more like a log line than a sentence
    until someone adds a real case for it."""
    actor = actor_name or "Someone"
    page = page_name or "this page"

    match entry.action:
        case "RECORD_CREATE":
            sentence = f"{actor} added a record to {page}"
        case "RECORD_UPDATE":
            changes = _diff_fields(entry.old_data, entry.new_data)
            if changes:
                key, old, new = changes[0]
                sentence = f"{actor} changed {key} in {page} from {old} to {new}"
            else:
                sentence = f"{actor} updated a record in {page}"
        case "RECORD_DELETE":
            reason = (entry.old_data or {}).get("reason")
            sentence = f"{actor} deleted a record from {page}"
            if reason:
                sentence += f" — {reason}"
        case "RECORD_REVERSE":
            sentence = f"{actor} reversed a record in {page}"
        case "PROTECTED_FIELD_CHANGE":
            column = (entry.new_data or {}).get("column", "a field")
            old = (entry.old_data or {}).get("value")
            new = (entry.new_data or {}).get("value")
            sentence = f"{actor} changed {column} in {page} from {old} to {new}"
        case "PAGE_CREATE":
            sentence = f"{actor} created the {page} page"
        case "PAGE_UPDATE":
            sentence = f"{actor} updated the {page} page"
        case "PAGE_ARCHIVE":
            sentence = f"{actor} archived the {page} page"
        case "PAGE_ACCESS_UPDATE":
            sentence = f"{actor} updated who can access {page}"
        case "COLUMN_CREATE":
            name = (entry.new_data or {}).get("name", "a column")
            sentence = f"{actor} added a '{name}' column to {page}"
        case "COLUMN_UPDATE":
            sentence = f"{actor} edited a column on {page}"
        case "CSV_EXPORT":
            count = (entry.new_data or {}).get("row_count")
            sentence = f"{actor} exported {page}"
            if count is not None:
                sentence += f" ({count} rows)"
        case "STORE_CREATE":
            name = (entry.new_data or {}).get("name", "a store")
            sentence = f"{actor} added the store '{name}'"
        case "STORE_UPDATE":
            sentence = f"{actor} updated a store"
        case "USER_CREATE":
            name = (entry.new_data or {}).get("full_name", "a user")
            sentence = f"{actor} added the user '{name}'"
        case "USER_UPDATE":
            sentence = f"{actor} updated a user"
        case "LOGIN":
            sentence = f"{actor} logged in"
        case "LOGIN_FAILED":
            sentence = f"A failed login attempt occurred for {actor}"
        case "PERMISSION_DENIED":
            sentence = f"{actor} attempted an action without permission"
        case _:
            action_words = entry.action.lower().replace("_", " ")
            sentence = f"{actor} performed {action_words} on {entry.entity_type}"

    if entry.source == "AI":
        sentence += " via AI"
    return sentence


def _to_entry(row: AuditLogRow) -> AuditLogEntry:
    entry, actor_name, page_name = row
    return AuditLogEntry(
        id=entry.id,
        created_at=entry.created_at,
        actor_name=actor_name,
        action=entry.action,
        entity_type=entry.entity_type,
        page_id=entry.page_id,
        page_name=page_name,
        source=entry.source,
        sentence=format_sentence(entry, actor_name, page_name),
        old_data=entry.old_data,
        new_data=entry.new_data,
    )


async def _viewable_page_ids(session: AsyncSession, ctx: SecurityContext) -> list[uuid.UUID] | None:
    """`None` means no restriction (Owner sees everything). A manager is
    restricted to pages they have `view` access to — `page_service.list_pages`
    already does exactly this join for `GET /pages`, reused here rather than
    a second copy of the same query."""
    if ctx.is_owner:
        return None
    pages = await page_service.list_pages(session, ctx)
    return [p.id for p in pages]


async def query_audit_logs(
    session: AsyncSession, ctx: SecurityContext, query: AuditLogQuery
) -> AuditLogPage:
    viewable_page_ids = await _viewable_page_ids(session, ctx)
    cursor = int(query.cursor) if query.cursor else None

    rows, has_more = await list_audit_logs(
        session,
        company_id=ctx.company_id,
        viewable_page_ids=viewable_page_ids,
        actor_user_id=query.actor_user_id,
        page_id=query.page_id,
        entity_type=query.entity_type,
        date_from=query.date_from,
        date_to=query.date_to,
        source=query.source,
        cursor=cursor,
        limit=query.limit,
    )
    items = [_to_entry(row) for row in rows]
    next_cursor = str(rows[-1][0].id) if has_more and rows else None
    return AuditLogPage(items=items, next_cursor=next_cursor, has_more=has_more)


async def export_audit_logs_csv(
    session: AsyncSession, ctx: SecurityContext, query: AuditLogQuery
) -> bytes:
    """Owner-only (enforced by the router) — every row matching the same
    filters as the read screen, oldest first so it reads like a log."""
    viewable_page_ids = await _viewable_page_ids(session, ctx)
    all_rows: list[AuditLogRow] = []
    cursor: int | None = int(query.cursor) if query.cursor else None
    while True:
        rows, has_more = await list_audit_logs(
            session,
            company_id=ctx.company_id,
            viewable_page_ids=viewable_page_ids,
            actor_user_id=query.actor_user_id,
            page_id=query.page_id,
            entity_type=query.entity_type,
            date_from=query.date_from,
            date_to=query.date_to,
            source=query.source,
            cursor=cursor,
            limit=500,
        )
        all_rows.extend(rows)
        if not has_more or not rows:
            break
        cursor = rows[-1][0].id

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Time", "Actor", "Action", "Page", "Description", "Source"])
    for entry, actor_name, page_name in reversed(all_rows):
        writer.writerow(
            [
                entry.created_at.isoformat(),
                actor_name or "",
                entry.action,
                page_name or "",
                format_sentence(entry, actor_name, page_name),
                entry.source,
            ]
        )
    return _BOM + buffer.getvalue().encode("utf-8")
