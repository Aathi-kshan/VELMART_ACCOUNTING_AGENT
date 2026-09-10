"""records (plan section 8.3)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Date,
    ForeignKey,
    Numeric,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    RecordStatus,
    TenantMixin,
    TimestampMixin,
    UUIDPKMixin,
    VersionMixin,
)


class Record(Base, UUIDPKMixin, TenantMixin, VersionMixin, TimestampMixin):
    __tablename__ = "records"
    # Indexes (ix_records_page_time, ix_records_data_gin, ix_records_num1,
    # ix_records_date1, ix_records_store, ux_records_client_uuid, ix_records_search)
    # are DESC-ordered / partial / expression indexes with custom operator classes
    # (jsonb_path_ops, gin_trgm_ops) — hand-authored as raw DDL in
    # alembic/versions/0002_page_engine.py, which is the source of truth for them.

    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False
    )
    store_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stores.id"))
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[RecordStatus] = mapped_column(
        SAEnum(RecordStatus, name="record_status", create_type=False),
        nullable=False,
        server_default=RecordStatus.ACTIVE.value,
    )
    reverses_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("records.id")
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

    # indexed projections, mapped per page via pages.projection_map
    num_1: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    num_2: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    num_3: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    num_4: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    date_1: Mapped[date | None] = mapped_column(Date)
    date_2: Mapped[date | None] = mapped_column(Date)
