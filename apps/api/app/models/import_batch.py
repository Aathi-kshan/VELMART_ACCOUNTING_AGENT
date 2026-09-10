"""import_batches (plan section 8.4)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, UUIDPKMixin


class ImportBatch(Base, UUIDPKMixin, TenantMixin):
    __tablename__ = "import_batches"

    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pages.id"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_rows: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    skipped_rows: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="PENDING")
    error_report: Mapped[dict | None] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
