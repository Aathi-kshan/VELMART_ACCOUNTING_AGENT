"""page_access (plan section 8.3)."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PageAccess(Base):
    __tablename__ = "page_access"

    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pages.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    can_view: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    can_create: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
