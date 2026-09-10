"""ai_sessions, ai_messages, ai_proposals, ai_proposal_items (plan section 8.6)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, UUIDPKMixin


class ProposalStatus(enum.StrEnum):
    PENDING = "PENDING"
    APPLIED = "APPLIED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    STALE = "STALE"


class AiSession(Base, UUIDPKMixin, TenantMixin):
    __tablename__ = "ai_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    last_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, server_default="0"
    )


class AiMessage(Base, UUIDPKMixin):
    __tablename__ = "ai_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)  # user|assistant|tool
    content: Mapped[str | None] = mapped_column(Text)
    tool_calls: Mapped[dict | None] = mapped_column(JSONB)
    tool_results: Mapped[dict | None] = mapped_column(JSONB)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class AiProposal(Base, UUIDPKMixin, TenantMixin):
    __tablename__ = "ai_proposals"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_sessions.id"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ProposalStatus] = mapped_column(
        SAEnum(ProposalStatus, name="proposal_status", create_type=False),
        nullable=False,
        server_default=ProposalStatus.PENDING.value,
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    applied_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class AiProposalItem(Base, UUIDPKMixin):
    __tablename__ = "ai_proposal_items"

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_proposals.id", ondelete="CASCADE"), nullable=False
    )
    operation: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # CREATE|UPDATE|STATUS_CHANGE|DELETE
    page_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("pages.id"))
    record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("records.id")
    )
    expected_version: Mapped[int | None] = mapped_column(Integer)
    before_data: Mapped[dict | None] = mapped_column(JSONB)
    after_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
