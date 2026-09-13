"""Request/response shapes for store management (docs/API.md, plan section 21.2)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class StoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    code: str
    name: str
    address: str | None
    is_active: bool


class CreateStoreRequest(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=500)


class UpdateStoreRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
