"""Request shapes for user management (docs/API.md, plan section 21.2)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=512)
    full_name: str = Field(min_length=1, max_length=200)
    role: UserRole
    store_ids: list[uuid.UUID] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    """Every field optional: a PATCH only touches what it sends.

    Changing `role` or `is_active` bumps `token_version` (plan section 20.2),
    invalidating every session that user currently holds — the same
    mechanism P1's test_token_version already proved works.
    """

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: UserRole | None = None
    is_active: bool | None = None
    store_ids: list[uuid.UUID] | None = None
