"""stores (plan section 8.2)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import TIMESTAMP, Boolean, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, UUIDPKMixin


class Store(Base, UUIDPKMixin, TenantMixin):
    __tablename__ = "stores"
    __table_args__ = (UniqueConstraint("company_id", "code"),)

    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
