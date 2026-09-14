"""Propose tools (P8 Lite) — the AI can prepare a change for the Owner's
review; it can never write business data. Every tool here does exactly one
thing at the database level: `session.add(AiProposal(...))`/
`AiProposalItem(...)`. Nothing here ever calls `update_row`/`create_row`/
`soft_delete_row` — the only path that ever touches a business table is the
Owner-approved `POST /ai/proposals/{id}/apply` (`app/ai/proposals.py`),
which reuses the exact same `record_service.update_record`/
`protected_field_service.set_protected_field` a human `PATCH` already calls.

`before_data`/`after_data` are always computed here from the database
(`repositories.records.get_row`), never from anything the model claims —
even if the model's stated "current value" is wrong, the proposal shown to
the Owner reflects reality. `record_id` must be a real id the model
obtained from an earlier read-tool call in the same conversation; it is
verified against the database (real row, right company, right page, not
deleted) before use, never assumed valid — see the module docstring in
`app/ai/tools/_shared.py` for the same principle applied to `page_key`.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools._shared import resolve_page
from app.ai.tools.registry import register_tool
from app.core.context import SecurityContext
from app.core.dates import now_utc
from app.core.errors import NotFoundError, ValidationFailedError
from app.models.ai import AiProposal, AiProposalItem, ProposalStatus
from app.models.page import Page, PageKind
from app.models.page_column import ColumnType, PageColumn
from app.repositories.records import RecordHandle, generated_columns_for, get_row, to_wire_value
from app.schemas.dynamic import build_record_model
from app.services import formula_service
from app.services.audit_service import write_audit_log
from app.services.record_service import validate_payload, validate_references

#: ADR 0004's number, kept as-is (plan section "Standing design decisions").
PROPOSAL_TTL_MINUTES = 10


def _protected_keys(columns: list[PageColumn]) -> set[str]:
    return {c.key for c in columns if c.is_protected}


async def _resolve_target_record(
    session: AsyncSession,
    ctx: SecurityContext,
    page: Page,
    columns: list[PageColumn],
    record_id_str: str,
) -> tuple[uuid.UUID, RecordHandle]:
    try:
        record_id = uuid.UUID(record_id_str)
    except ValueError as exc:
        raise ValidationFailedError(f"{record_id_str!r} is not a valid record id.") from exc

    handle = await get_row(session, page, columns, record_id, ctx.company_id)
    if handle is None or handle.is_deleted:
        raise NotFoundError("No such record.")
    return record_id, handle


def _compute_before_after(
    columns: list[PageColumn], handle: RecordHandle, page: Page, changes: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """`handle.data` is already wire format (a money string, ISO date text —
    plan section 9.1) and never carries a FORMULA key (never stored).
    `changes` is Python-typed, straight out of pydantic's `.model_dump()` —
    `update_row` normally wire-converts as a side effect of writing and
    re-reading the row; a proposal never writes, so it does the same
    conversion explicitly here before computing the formula impact."""
    columns_by_key = {c.key: c for c in columns}
    generated = generated_columns_for(page)

    before_data = formula_service.apply_formulas(columns, dict(handle.data))

    merged = dict(handle.data)
    merged.update(changes)
    for key in generated:
        merged.pop(key, None)
    full_validated = validate_payload(columns, merged, readonly_extra=generated)
    wire_after = {
        key: to_wire_value(columns_by_key[key], value)
        for key, value in full_validated.items()
        if key in columns_by_key
    }
    after_data = formula_service.apply_formulas(columns, wire_after)
    return before_data, after_data


async def _create_proposal(
    session: AsyncSession,
    ctx: SecurityContext,
    ai_session_id: uuid.UUID,
    *,
    page: Page,
    record_id: uuid.UUID,
    handle: RecordHandle,
    operation: str,
    before_data: dict[str, Any],
    after_data: dict[str, Any],
    summary: str,
) -> dict[str, Any]:
    proposal = AiProposal(
        company_id=ctx.company_id,
        session_id=ai_session_id,
        created_by=ctx.user_id,
        summary=summary,
        status=ProposalStatus.PENDING,
        expires_at=now_utc() + timedelta(minutes=PROPOSAL_TTL_MINUTES),
    )
    session.add(proposal)
    await session.flush()

    session.add(
        AiProposalItem(
            proposal_id=proposal.id,
            operation=operation,
            page_id=page.id,
            record_id=record_id,
            expected_version=handle.version,
            before_data=before_data,
            after_data=after_data,
            position=0,
        )
    )
    await session.flush()

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="AI_PROPOSAL_CREATED",
        entity_type="ai_proposal",
        entity_id=proposal.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        new_data={"summary": summary, "record_id": str(record_id)},
        source="AI",
        ai_session_id=ai_session_id,
    )

    return {
        "proposal_id": str(proposal.id),
        "summary": summary,
        "expires_at": proposal.expires_at.isoformat(),
        "page": page.name,
        "before": before_data,
        "after": after_data,
    }


# --------------------------------------------------------------------------
# propose_update
# --------------------------------------------------------------------------


class ProposeUpdateParams(BaseModel):
    page_key: str = Field(description="A page key returned by list_pages.")
    record_id: str = Field(
        description=(
            "A real record id obtained from an earlier list_pages/query_records/"
            "search_records/search_entities call in this conversation — never invented."
        )
    )
    changes: dict[str, Any] = Field(
        description="Column key -> new value (wire format, e.g. money as a decimal string)."
    )
    reason: str | None = Field(
        default=None, description="A short note shown to the Owner explaining the change."
    )


async def propose_update(
    *,
    ctx: SecurityContext,
    session: AsyncSession,
    ai_session_id: uuid.UUID,
    params: ProposeUpdateParams,
) -> dict[str, Any]:
    page, columns = await resolve_page(session, ctx, params.page_key)
    if page.kind is PageKind.LEDGER:
        raise ValidationFailedError(
            "Ledger-style page records are corrected by reversal, not a direct edit — "
            "this page cannot be targeted by propose_update."
        )

    record_id, handle = await _resolve_target_record(session, ctx, page, columns, params.record_id)

    touched_protected = _protected_keys(columns) & params.changes.keys()
    if touched_protected:
        raise ValidationFailedError(
            f"{sorted(touched_protected)} are protected field(s) — "
            "use propose_status_change instead."
        )

    generated = generated_columns_for(page)
    partial_model = build_record_model(columns, partial=True, readonly_extra=generated)
    try:
        validated_changes = partial_model(**params.changes).model_dump(exclude_unset=True)
    except ValidationError as exc:
        raise ValidationFailedError(
            "The proposed change did not match this page's schema.",
            extra={"errors": exc.errors(include_url=False, include_context=False)},
        ) from exc

    if not validated_changes:
        raise ValidationFailedError("No real change was proposed.")

    await validate_references(session, ctx, columns, validated_changes)

    before_data, after_data = _compute_before_after(columns, handle, page, validated_changes)
    summary = f"Update {page.name}" + (f" — {params.reason}" if params.reason else "")

    return await _create_proposal(
        session,
        ctx,
        ai_session_id,
        page=page,
        record_id=record_id,
        handle=handle,
        operation="UPDATE",
        before_data=before_data,
        after_data=after_data,
        summary=summary,
    )


register_tool(
    propose_update,
    name="propose_update",
    description=(
        "Propose changing one or more fields on a single existing record. "
        "This never writes the change directly — it creates a pending "
        "proposal that the Owner must review and approve. record_id must "
        "come from an earlier tool call's real results in this "
        "conversation, never invented. Protected fields (e.g. a status "
        "column) must go through propose_status_change instead."
    ),
    params_model=ProposeUpdateParams,
    kind="propose",
)


# --------------------------------------------------------------------------
# propose_status_change
# --------------------------------------------------------------------------


class ProposeStatusChangeParams(BaseModel):
    page_key: str = Field(description="A page key returned by list_pages.")
    record_id: str = Field(
        description="A real record id obtained from an earlier tool call — never invented."
    )
    column_key: str = Field(description="A protected SELECT column's key, from get_page_schema.")
    value: str = Field(
        description="The new value — must be one of the column's configured options."
    )


async def propose_status_change(
    *,
    ctx: SecurityContext,
    session: AsyncSession,
    ai_session_id: uuid.UUID,
    params: ProposeStatusChangeParams,
) -> dict[str, Any]:
    page, columns = await resolve_page(session, ctx, params.page_key)
    record_id, handle = await _resolve_target_record(session, ctx, page, columns, params.record_id)

    columns_by_key = {c.key: c for c in columns}
    column = columns_by_key.get(params.column_key)
    if column is None or not column.is_protected or column.data_type is not ColumnType.SELECT:
        raise ValidationFailedError(f"{params.column_key!r} is not a protected field on this page.")

    options = column.config.get("options") or []
    if params.value not in options:
        raise ValidationFailedError(f"{column.name}: must be one of {options}.")

    before_data, after_data = _compute_before_after(
        columns, handle, page, {params.column_key: params.value}
    )
    summary = f"Change {column.name} on {page.name} to {params.value!r}"

    return await _create_proposal(
        session,
        ctx,
        ai_session_id,
        page=page,
        record_id=record_id,
        handle=handle,
        operation="STATUS_CHANGE",
        before_data=before_data,
        after_data=after_data,
        summary=summary,
    )


register_tool(
    propose_status_change,
    name="propose_status_change",
    description=(
        "Propose changing a protected status-style field (e.g. a cheque's "
        "status) on a single existing record — the only way to propose a "
        "change to a protected column; propose_update refuses them. Never "
        "writes directly; creates a pending proposal for the Owner to "
        "approve."
    ),
    params_model=ProposeStatusChangeParams,
    kind="propose",
)
