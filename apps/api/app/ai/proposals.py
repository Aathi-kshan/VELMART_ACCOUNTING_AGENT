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
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.dates import now_utc
from app.core.errors import (
    ConflictError,
    NotFoundError,
    ProposalExpiredError,
    ProposalStaleError,
    ValidationFailedError,
)
from app.models.ai import AiProposal, AiProposalItem, ProposalStatus
from app.models.page import Page
from app.models.page_column import ColumnType, PageColumn
from app.repositories.records import generated_columns_for, get_row
from app.schemas.record import UpdateRecordRequest
from app.services import page_service, protected_field_service, record_service
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


def _derive_delta(
    item: AiProposalItem, columns_by_key: dict[str, PageColumn], page: Page
) -> dict[str, Any]:
    """The real change to apply: every key where `after_data` differs from
    `before_data`, excluding FORMULA columns (computed, never settable —
    `build_record_model` doesn't even accept them as a field) and generated
    columns (same reason). `before_data`/`after_data` were computed once,
    at proposal-creation time, by this exact same rule (plan section
    "Standing design decisions") — the Owner-facing diff and the delta
    actually applied here are guaranteed to be the same computation."""
    generated = generated_columns_for(page)
    before_data = item.before_data or {}
    return {
        key: value
        for key, value in item.after_data.items()
        if before_data.get(key) != value
        and key in columns_by_key
        and columns_by_key[key].data_type is not ColumnType.FORMULA
        and key not in generated
    }


async def _apply_one_item(
    session: AsyncSession, ctx: SecurityContext, proposal: AiProposal, item: AiProposalItem
) -> None:
    if item.page_id is None or item.record_id is None:
        raise ValidationFailedError("This proposal item is missing a target page or record.")
    record_id = item.record_id

    page = await session.get(Page, item.page_id)
    if page is None or page.company_id != ctx.company_id:
        raise NotFoundError("The target page no longer exists.")
    columns = await page_service.get_page_columns(session, page.id)
    columns_by_key = {c.key: c for c in columns}

    handle = await get_row(session, page, columns, record_id, ctx.company_id)
    if handle is None or handle.is_deleted:
        raise NotFoundError("The target record no longer exists.")
    if handle.version != item.expected_version:
        raise ProposalStaleError(
            f"This record has changed since the proposal was created "
            f"(now at version {handle.version}).",
            extra={"current_version": handle.version},
        )

    delta = _derive_delta(item, columns_by_key, page)

    if item.operation == "UPDATE":
        await record_service.update_record(
            session,
            ctx,
            record_id,
            UpdateRecordRequest(data=delta),
            item.expected_version,
            source="AI",
            ai_session_id=proposal.session_id,
        )
    elif item.operation == "STATUS_CHANGE":
        if len(delta) != 1:
            raise ValidationFailedError("A status-change proposal must change exactly one field.")
        ((column_key, value),) = delta.items()
        await protected_field_service.set_protected_field(
            session,
            ctx,
            record_id,
            column_key,
            str(value),
            item.expected_version,
            source="AI",
            ai_session_id=proposal.session_id,
        )
    else:
        raise ValidationFailedError(f"Unknown proposal operation: {item.operation!r}")


async def apply_proposal(
    session: AsyncSession, ctx: SecurityContext, proposal_id: uuid.UUID
) -> AiProposal:
    """Re-validates and applies every item of a `PENDING`, unexpired
    proposal in this one request's transaction (`get_rls_session` already
    wraps the whole request in `session.begin()`) — any exception anywhere
    in this sequence propagates uncaught, rolling everything back. No
    partial apply, ever."""
    proposal = await _get_owned_proposal(session, ctx, proposal_id)

    if proposal.status is not ProposalStatus.PENDING:
        raise ConflictError(
            f"This proposal is already {proposal.status.value.lower()} and cannot be applied."
        )

    if now_utc() > proposal.expires_at:
        proposal.status = ProposalStatus.EXPIRED
        raise ProposalExpiredError(
            "This proposal had already expired — nothing was applied. "
            "Ask the AI to propose the change again."
        )

    items = list(
        (
            await session.execute(
                select(AiProposalItem)
                .where(AiProposalItem.proposal_id == proposal.id)
                .order_by(AiProposalItem.position)
            )
        )
        .scalars()
        .all()
    )

    for item in items:
        await _apply_one_item(session, ctx, proposal, item)

    proposal.status = ProposalStatus.APPLIED
    proposal.applied_at = now_utc()
    proposal.applied_by = ctx.user_id
    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="AI_PROPOSAL_APPLIED",
        entity_type="ai_proposal",
        entity_id=proposal.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        source="AI",
        ai_session_id=proposal.session_id,
    )
    return proposal
