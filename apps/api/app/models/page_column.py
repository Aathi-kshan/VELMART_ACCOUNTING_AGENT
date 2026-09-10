"""page_columns (plan section 8.3)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPKMixin


class ColumnType(enum.StrEnum):
    TEXT = "TEXT"
    LONG_TEXT = "LONG_TEXT"
    NUMBER = "NUMBER"
    CURRENCY = "CURRENCY"
    PERCENT = "PERCENT"
    DATE = "DATE"
    DATETIME = "DATETIME"
    BOOLEAN = "BOOLEAN"
    SELECT = "SELECT"
    MULTI_SELECT = "MULTI_SELECT"
    RECORD_REF = "RECORD_REF"
    STORE_REF = "STORE_REF"
    USER_REF = "USER_REF"
    FORMULA = "FORMULA"
    ATTACHMENT = "ATTACHMENT"


class PageColumn(Base, UUIDPKMixin):
    __tablename__ = "page_columns"
    __table_args__ = (UniqueConstraint("page_id", "key"),)

    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    data_type: Mapped[ColumnType] = mapped_column(
        SAEnum(ColumnType, name="column_type", create_type=False), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_indexed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_protected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    description: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
