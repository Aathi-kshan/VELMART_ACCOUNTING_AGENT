"""dashboard_widgets (plan section 8.4)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, UUIDPKMixin
from app.models.user import UserRole


class DashboardWidget(Base, UUIDPKMixin, TenantMixin):
    __tablename__ = "dashboard_widgets"

    page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pages.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    widget_type: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # METRIC|TREND|BREAKDOWN|LIST|REVIEW_QUEUE
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    visible_to: Mapped[UserRole | None] = mapped_column(
        SAEnum(UserRole, name="user_role", create_type=False)
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
