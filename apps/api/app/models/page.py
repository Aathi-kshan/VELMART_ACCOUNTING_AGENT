"""pages (plan section 8.3 — the page engine)."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPKMixin


class PageKind(enum.StrEnum):
    REGISTER = "REGISTER"
    LEDGER = "LEDGER"


class Page(Base, UUIDPKMixin, TenantMixin, TimestampMixin):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("company_id", "key"),)

    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[PageKind] = mapped_column(
        SAEnum(PageKind, name="page_kind", create_type=False),
        nullable=False,
        server_default=PageKind.REGISTER.value,
    )
    date_column_key: Mapped[str | None] = mapped_column(Text)
    store_column_key: Mapped[str | None] = mapped_column(Text)
    #: The NUMBER/CURRENCY column `GET /pages/{id}/running-balance` sums
    #: cumulatively over this page's rows (P4 §8) — only meaningful on a
    #: `kind = LEDGER` page.
    balance_column_key: Mapped[str | None] = mapped_column(Text)
    projection_map: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    # A system page is a schema descriptor for a natively-stored business table
    # (ADR 0006). Its rows live in `storage_table`, never in `records`, and its
    # schema changes by migration rather than through the API.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    storage_table: Mapped[str | None] = mapped_column(Text)
