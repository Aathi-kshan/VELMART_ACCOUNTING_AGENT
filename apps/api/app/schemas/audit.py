"""Audit log read API (plan section 18.3, P5) — the Owner-facing view.

`AuditLogEntry.sentence` is server-formatted (`app/services/
audit_read_service.py`) — the client renders it directly, never rebuilding
the human-language description itself. Date-header grouping ("Today"/
"Yesterday") is left to the client: it depends on the viewer's own
timezone, which isn't tracked anywhere server-side.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class AuditLogEntry(BaseModel):
    id: int
    created_at: datetime
    actor_name: str | None
    action: str
    entity_type: str
    page_id: uuid.UUID | None
    page_name: str | None
    source: str
    sentence: str
    old_data: dict | None
    new_data: dict | None


class AuditLogPage(BaseModel):
    items: list[AuditLogEntry]
    next_cursor: str | None = None
    has_more: bool = False


class AuditLogQuery(BaseModel):
    actor_user_id: uuid.UUID | None = None
    page_id: uuid.UUID | None = None
    entity_type: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    source: str | None = None
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
