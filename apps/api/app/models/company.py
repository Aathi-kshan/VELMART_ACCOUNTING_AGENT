"""companies, company_settings (plan section 8.2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    TIMESTAMP,
    Boolean,
    ForeignKey,
    Numeric,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Company(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="LKR")
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="Asia/Colombo")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class CompanySettings(Base):
    __tablename__ = "company_settings"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    day_cutoff_hour: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="2")
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    ai_daily_usd_cap: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, server_default="3.00"
    )
    ai_model_config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    ai_allow_delete_proposals: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
