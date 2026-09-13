"""daily_digests (P5 §nightly-ops, migration 0013) — one structured summary
row per company per day, written by `app/tasks/daily_digest.py`."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import TIMESTAMP, Date, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, UUIDPKMixin


class DailyDigest(Base, UUIDPKMixin, TenantMixin):
    __tablename__ = "daily_digests"
    __table_args__ = (UniqueConstraint("company_id", "digest_date"),)

    digest_date: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
