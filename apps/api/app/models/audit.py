"""audit_logs (plan section 8.5 / 18.1).

Append-only and hash-chained: row_hash / prev_hash are computed by the
`fn_audit_logs_hash_chain` Postgres trigger (alembic/versions/0005_audit_trigger_hashchain.py),
never by application code, and `app_user` has UPDATE/DELETE/TRUNCATE revoked on this table.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, BigInteger, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.user import UserRole


class AuditAction(enum.StrEnum):
    """Every `action` string actually passed to `write_audit_log` in this
    codebase, kept in sync by hand (P5) — `action` itself is stored and typed
    as plain `str` everywhere, never validated against this enum at write
    time, so this is documentation and the read-side sentence formatter's
    (`app/services/audit_read_service.py`) exhaustiveness reference, not an
    enforced constraint. Re-grep `write_audit_log(` across `app/` before
    trusting this list is still complete.
    """

    RECORD_CREATE = "RECORD_CREATE"
    RECORD_UPDATE = "RECORD_UPDATE"
    RECORD_DELETE = "RECORD_DELETE"
    RECORD_REVERSE = "RECORD_REVERSE"
    PROTECTED_FIELD_CHANGE = "PROTECTED_FIELD_CHANGE"
    LOGIN = "LOGIN"
    LOGIN_FAILED = "LOGIN_FAILED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    CSV_EXPORT = "CSV_EXPORT"
    PAGE_CREATE = "PAGE_CREATE"
    PAGE_UPDATE = "PAGE_UPDATE"
    PAGE_ARCHIVE = "PAGE_ARCHIVE"
    PAGE_ACCESS_UPDATE = "PAGE_ACCESS_UPDATE"
    COLUMN_CREATE = "COLUMN_CREATE"
    COLUMN_UPDATE = "COLUMN_UPDATE"
    STORE_CREATE = "STORE_CREATE"
    STORE_UPDATE = "STORE_UPDATE"
    USER_CREATE = "USER_CREATE"
    USER_UPDATE = "USER_UPDATE"
    #: P5 — dashboard widgets (plan section 15, §18.2's "Dashboard widget
    #: added / changed").
    AI_PROPOSAL_CREATED = "AI_PROPOSAL_CREATED"
    AI_PROPOSAL_APPLIED = "AI_PROPOSAL_APPLIED"
    AI_PROPOSAL_CANCELLED = "AI_PROPOSAL_CANCELLED"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_role: Mapped[UserRole | None] = mapped_column(
        SAEnum(UserRole, name="user_role", create_type=False)
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    page_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    old_data: Mapped[dict | None] = mapped_column(JSONB)
    new_data: Mapped[dict | None] = mapped_column(JSONB)
    diff: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(Text, nullable=False)  # APP | AI | CSV | SYSTEM
    ai_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    prev_hash: Mapped[str | None] = mapped_column(Text)
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
