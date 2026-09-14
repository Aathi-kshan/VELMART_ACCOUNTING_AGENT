"""`POST /ai/sessions` / `POST /ai/sessions/{id}/messages` (plan section
16.2, P7.6; docs/API.md §9) — Owner-only at every layer: `require_owner`
here, the orchestrator re-checks nothing extra (the guard already 403s a
manager and audits the denial), and every AI tool only ever runs against
the caller's own company via `get_ai_reader_session`.

`POST /ai/proposals/{id}/cancel` (P8 Slice 5) and `.../apply` (Slice 6) are
the only two things an Owner ever does to a pending proposal — both run on
`get_rls_session` like every other mutating endpoint in this app, never the
read-only `ai_reader_session`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import orchestrator, proposals
from app.core.context import SecurityContext
from app.dependencies.db import get_ai_reader_session, get_rls_session
from app.dependencies.guards import require_owner
from app.schemas.ai import (
    ProposalStatusResponse,
    ProvenanceOut,
    SendAiMessageRequest,
    SendAiMessageResponse,
    StartAiSessionResponse,
    ToolCallOut,
)

router = APIRouter(tags=["ai"])


@router.post("/ai/sessions", response_model=StartAiSessionResponse, status_code=201)
async def create_ai_session(
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> StartAiSessionResponse:
    ai_session = await orchestrator.start_session(session, ctx)
    return StartAiSessionResponse(id=ai_session.id, started_at=ai_session.started_at)


@router.post("/ai/sessions/{session_id}/messages", response_model=SendAiMessageResponse)
async def send_ai_message(
    session_id: uuid.UUID,
    payload: SendAiMessageRequest,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
    ai_reader_session: AsyncSession = Depends(get_ai_reader_session),
) -> SendAiMessageResponse:
    result = await orchestrator.send_message(
        session, ai_reader_session, ctx, session_id, payload.message
    )
    return SendAiMessageResponse(
        message_id=result.message_id,
        answer=result.answer,
        provenance=[
            ProvenanceOut(
                page=p.page, record_count=p.record_count, date_from=p.date_from, date_to=p.date_to
            )
            for p in result.provenance
        ],
        tool_calls=[
            ToolCallOut(tool=c["tool"], duration_ms=c["duration_ms"]) for c in result.tool_calls
        ],
        proposal=None,
        cost_usd=str(result.cost_usd),
        partial=result.partial,
    )


@router.post("/ai/proposals/{proposal_id}/cancel", response_model=ProposalStatusResponse)
async def cancel_ai_proposal(
    proposal_id: uuid.UUID,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> ProposalStatusResponse:
    proposal = await proposals.cancel_proposal(session, ctx, proposal_id)
    return ProposalStatusResponse(id=proposal.id, status=proposal.status.value)


@router.post("/ai/proposals/{proposal_id}/apply", response_model=ProposalStatusResponse)
async def apply_ai_proposal(
    proposal_id: uuid.UUID,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> ProposalStatusResponse:
    proposal = await proposals.apply_proposal(session, ctx, proposal_id)
    return ProposalStatusResponse(id=proposal.id, status=proposal.status.value)
