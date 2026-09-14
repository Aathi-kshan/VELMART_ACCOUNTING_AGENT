"""Request/response shapes for the AI read/propose endpoints (plan section
16, P7.6, P8 Lite; docs/API.md §9). `proposal` is now populated for real
(P8) when the AI called `propose_update`/`propose_status_change` while
answering a message — the same shape `app/ai/proposals.py`'s apply-time
delta derivation is built from, so what the Owner sees here is guaranteed
to match what applying it would actually do.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StartAiSessionResponse(BaseModel):
    id: uuid.UUID
    started_at: datetime


class SendAiMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ToolCallOut(BaseModel):
    tool: str
    duration_ms: int


class ProvenanceOut(BaseModel):
    #: Wire field names match docs/API.md §9 (`from`/`to`) — `date_from`/
    #: `date_to` internally (`app/ai/provenance.py`) to avoid the Python
    #: keyword collision `from` would cause as an attribute name.
    model_config = ConfigDict(populate_by_name=True)

    page: str
    record_count: int
    date_from: str | None = Field(default=None, alias="from")
    date_to: str | None = Field(default=None, alias="to")


class ProposalChangeOut(BaseModel):
    column: str
    before: Any
    after: Any


class ProposalOut(BaseModel):
    id: str
    summary: str
    expires_at: str
    page: str
    changes: list[ProposalChangeOut]


class SendAiMessageResponse(BaseModel):
    message_id: uuid.UUID
    answer: str
    provenance: list[ProvenanceOut] = Field(default_factory=list)
    tool_calls: list[ToolCallOut] = Field(default_factory=list)
    proposal: ProposalOut | None = None
    cost_usd: str
    partial: bool


class ProposalStatusResponse(BaseModel):
    """`POST /ai/proposals/{id}/cancel` — and `.../apply` (P8 Slice 6)."""

    id: uuid.UUID
    status: str
