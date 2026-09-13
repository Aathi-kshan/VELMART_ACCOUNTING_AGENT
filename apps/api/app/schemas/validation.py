"""`page_validations` — Owner-authored ERROR/WARNING rules over a page's own
column values and its computed FORMULA results (plan section 11.3, P4 §6;
docs/API.md §4).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ValidationRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    expression: str = Field(min_length=1, max_length=500)
    severity: Literal["ERROR", "WARNING"] = "ERROR"
    message: str = Field(min_length=1, max_length=500)


class ValidationRuleUpdate(BaseModel):
    """Every field optional: a PATCH only touches what it sends — the same
    convention as `UpdateColumnRequest`. `DELETE /validations/{id}` is a thin
    wrapper that sends only `is_active=False` (the column-archive pattern)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    expression: str | None = Field(default=None, min_length=1, max_length=500)
    severity: Literal["ERROR", "WARNING"] | None = None
    message: str | None = Field(default=None, min_length=1, max_length=500)
    is_active: bool | None = None


class ValidationRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    page_id: uuid.UUID
    name: str
    expression: str
    severity: str
    message: str
    is_active: bool
    created_at: datetime
