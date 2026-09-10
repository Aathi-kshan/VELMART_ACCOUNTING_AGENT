"""Declarative base and shared column mixins (plan section 8.1)."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RecordStatus(enum.StrEnum):
    """The `record_status` enum, shared by `records` and the business tables."""

    ACTIVE = "ACTIVE"
    REVERSED = "REVERSED"
    VOID = "VOID"


class UUIDPKMixin:
    """id UUID PRIMARY KEY DEFAULT gen_random_uuid()"""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )


class TenantMixin:
    """company_id UUID NOT NULL REFERENCES companies(id)"""

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )


class TimestampMixin:
    """created_at / updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"""

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class VersionMixin:
    """version INTEGER NOT NULL DEFAULT 1 -- optimistic locking"""

    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")


class BusinessTableMixin(UUIDPKMixin, TenantMixin, VersionMixin, TimestampMixin):
    """Platform columns shared by the natively-stored business tables (plan section 8.9).

    Mirrors the platform half of `records` so the service layer can treat both
    storage backends uniformly. Business columns are declared on each subclass.
    """

    store_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id"))
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        SAEnum(RecordStatus, name="record_status", create_type=False),
        nullable=False,
        server_default=RecordStatus.ACTIVE.value,
    )
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="APP")
    client_uuid: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    deleted_reason: Mapped[str | None] = mapped_column(Text)
