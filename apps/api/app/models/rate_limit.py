"""rate_limits (plan section 5.3 / 20.3)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import TIMESTAMP, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RateLimit(Base):
    """One fixed window for one bucket.

    No company_id and no RLS: login throttling runs before the company is known.
    """

    __tablename__ = "rate_limits"

    bucket_key: Mapped[str] = mapped_column(Text, primary_key=True)
    window_start: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
