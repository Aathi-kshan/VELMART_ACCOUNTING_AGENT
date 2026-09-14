"""Proposal lifecycle — cancel and apply (P8 Lite, ADR 0004). The only two
things an Owner ever does to a pending proposal, both Owner-only
(`app/routers/ai.py`'s `require_owner`).

Expiry is lazy, by design (the brief's own "use `expires_at` rather than a
scheduling system"): nothing sweeps `PENDING` rows on a timer. Whichever of
`cancel_proposal`/`apply_proposal` happens to touch an expired proposal
first is what discovers and persists the `EXPIRED` transition.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.dates import now_utc
from app.core.errors import ConflictError, NotFoundError, ProposalExpiredError
from app.models.ai import AiProposal, ProposalStatus
from app.services.audit_service import write_audit_log


async def _get_owned_proposal(
    session: AsyncSession, ctx: SecurityContext, proposal_id: uuid.UUID
) -> AiProposal:
    proposal = await session.get(AiProposal, proposal_id)
    if proposal is None or proposal.company_id != ctx.company_id:
        raise NotFoundError("No such proposal.")
    return proposal


async def cancel_proposal(
    session: AsyncSession, ctx: SecurityContext, proposal_id: uuid.UUID
) -> AiProposal:
    proposal = await _get_owned_proposal(session, ctx, proposal_id)

    if proposal.status is ProposalStatus.CANCELLED:
        return proposal  # repeated cancellation is safe — idempotent no-op

    if proposal.status is not ProposalStatus.PENDING:
        raise ConflictError(
            f"This proposal is already {proposal.status.value.lower()} and cannot be cancelled."
        )

    if now_utc() > proposal.expires_at:
        proposal.status = ProposalStatus.EXPIRED
        raise ProposalExpiredError(
            "This proposal had already expired — nothing was cancelled. "
            "Ask the AI to propose the change again."
        )

    proposal.status = ProposalStatus.CANCELLED
    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="AI_PROPOSAL_CANCELLED",
        entity_type="ai_proposal",
        entity_id=proposal.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        source="AI",
        ai_session_id=proposal.session_id,
    )
    return proposal
