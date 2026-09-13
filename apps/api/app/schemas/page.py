"""Request/response shapes for page management (plan sections 8.3, 10.1,
21.2; docs/API.md §4).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.page import PageKind
from app.schemas.column import ColumnDefinition, ColumnOut
from app.schemas.validation import ValidationRuleOut


class CreatePageRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: PageKind = PageKind.REGISTER
    description: str | None = None
    icon: str | None = None
    columns: list[ColumnDefinition] = Field(default_factory=list)
    #: The *derived* key (the same lowercase/underscore slug the server will
    #: assign to that column's name) of one of the `columns` above — the
    #: server validates this after deriving every column's key, and rejects
    #: with the actual valid keys listed if it doesn't match one of the
    #: right type (DATE/DATETIME for date_column_key, STORE_REF for
    #: store_column_key). See page_service.create_page.
    date_column_key: str | None = None
    store_column_key: str | None = None
    #: NUMBER/CURRENCY only — the column `GET /pages/{id}/running-balance`
    #: sums cumulatively (P4 §8). Meaningful only on a `kind=LEDGER` page,
    #: but not enforced as such: an Owner may set it up before or after
    #: deciding a page is ledger-style.
    balance_column_key: str | None = None

    @model_validator(mode="after")
    def _unique_column_names(self) -> CreatePageRequest:
        names = [c.name.strip().lower() for c in self.columns]
        if len(names) != len(set(names)):
            raise ValueError("Column names must be unique on a page.")
        return self


class UpdatePageRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    icon: str | None = None
    date_column_key: str | None = None
    store_column_key: str | None = None
    balance_column_key: str | None = None


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    key: str
    name: str
    kind: PageKind
    description: str | None
    icon: str | None
    date_column_key: str | None
    store_column_key: str | None
    balance_column_key: str | None
    is_archived: bool
    is_system: bool
    storage_table: str | None
    version: int


class PageSchemaOut(PageOut):
    columns: list[ColumnOut] = Field(default_factory=list)
    #: Column keys that are DB-computed on this page's storage table
    #: (`app.repositories.records.GENERATED_COLUMNS`) — e.g.
    #: `daily_revenue.total_revenue`. Always empty for a generic
    #: (non-system) page. A client renders these read-only: the write API
    #: rejects any value supplied for one (plan section 3.5.8).
    generated_columns: list[str] = Field(default_factory=list)
    #: Active `page_validations` rules (P4 §6) — archived ones are omitted,
    #: same as `columns` already omits archived columns.
    validations: list[ValidationRuleOut] = Field(default_factory=list)


class AccessGrant(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    can_view: bool = True
    can_create: bool = True


class PutPageAccessRequest(BaseModel):
    grants: list[AccessGrant] = Field(default_factory=list)
