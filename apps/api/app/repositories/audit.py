"""Read-side query builder for `audit_logs` (plan section 18.3, P5).

`AuditLog` is a fixed-shape table (unlike `records`, a per-page dynamic
one) — plain SQLAlchemy `select()`, no dynamic-column machinery and no
injection-safety boundary to build here, since nothing accepts an arbitrary
column-name string from the client.

Pagination is a single `id DESC` cursor, not `query_service.py`'s generic
multi-key keyset — `id` is a `BIGSERIAL` written in strict insertion order
by the hash-chain trigger (migration 0005), so sorting on it alone already
matches `created_at DESC` with no possible tie, and needs no second sort key
to stay stable.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.page import Page
from app.models.user import User

#: One row: the audit entry plus the two names a sentence needs, joined in
#: rather than resolved per-row afterward — avoids an N+1 for a page of entries.
AuditLogRow = tuple[AuditLog, str | None, str | None]


async def list_audit_logs(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    viewable_page_ids: list[uuid.UUID] | None,
    actor_user_id: uuid.UUID | None,
    page_id: uuid.UUID | None,
    entity_type: str | None,
    date_from: date | None,
    date_to: date | None,
    source: str | None,
    cursor: int | None,
    limit: int,
) -> tuple[list[AuditLogRow], bool]:
    """`viewable_page_ids=None` means no restriction (an Owner call) — a
    non-`None`, possibly-empty list restricts to exactly those pages, which
    also correctly excludes every `page_id IS NULL` row (a manager never
    sees logins, user/store/settings changes, or permission denials — plan
    section 18.3's own examples are all page-scoped)."""
    conditions = [AuditLog.company_id == company_id]
    if viewable_page_ids is not None:
        conditions.append(AuditLog.page_id.in_(viewable_page_ids))
    if actor_user_id is not None:
        conditions.append(AuditLog.actor_user_id == actor_user_id)
    if page_id is not None:
        conditions.append(AuditLog.page_id == page_id)
    if entity_type is not None:
        conditions.append(AuditLog.entity_type == entity_type)
    if date_from is not None:
        conditions.append(AuditLog.created_at >= datetime.combine(date_from, time.min))
    if date_to is not None:
        next_day = datetime.combine(date_to + timedelta(days=1), time.min)
        conditions.append(AuditLog.created_at < next_day)
    if source is not None:
        conditions.append(AuditLog.source == source)
    if cursor is not None:
        conditions.append(AuditLog.id < cursor)

    stmt = (
        select(AuditLog, User.full_name, Page.name)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .outerjoin(Page, Page.id == AuditLog.page_id)
        .where(*conditions)
        .order_by(AuditLog.id.desc())
        .limit(limit + 1)
    )
    result = await session.execute(stmt)
    rows: list[AuditLogRow] = [
        (entry, actor_name, page_name) for entry, actor_name, page_name in result
    ]
    has_more = len(rows) > limit
    return rows[:limit], has_more
