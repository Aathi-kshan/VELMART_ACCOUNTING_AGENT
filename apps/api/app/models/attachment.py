"""attachments (plan section 8.4)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, BigInteger, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, UUIDPKMixin


class Attachment(Base, UUIDPKMixin, TenantMixin):
    __tablename__ = "attachments"

    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("records.id", ondelete="CASCADE"), nullable=False
    )
    column_key: Mapped[str | None] = mapped_column(Text)
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
