"""user_role, users, user_stores, refresh_tokens, idempotency_keys (plan section 8.2)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPKMixin


class UserRole(enum.StrEnum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"


class User(Base, UUIDPKMixin, TenantMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("company_id", "email"),)

    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", create_type=False), nullable=False
    )
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class UserStore(Base):
    __tablename__ = "user_stores"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True
    )


class RefreshToken(Base, UUIDPKMixin):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    device_id: Mapped[str] = mapped_column(Text, nullable=False)
    device_name: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_tokens.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class IdempotencyKey(Base):
    """idempotency without Redis; the nightly job deletes rows older than 48h."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_body: Mapped[dict | None] = mapped_column(JSONB)
    status_code: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
