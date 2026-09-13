"""`page_validations` — Owner-authored ERROR/WARNING rules evaluated over a
record's write-time values: its own validated data plus its just-computed
`FORMULA` results (plan section 11.3, P4 §6). Never evaluated at read time —
a rule exists to gate a write, not to annotate a response.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.errors import ExpressionSecurityError, NotFoundError
from app.core.expressions.evaluator import FormulaEvaluationError
from app.core.expressions.evaluator import evaluate as evaluate_expression
from app.core.expressions.parser import parse_expression
from app.models.page import Page
from app.models.page_column import PageColumn
from app.models.page_validation import PageValidation
from app.schemas.validation import ValidationRuleCreate, ValidationRuleUpdate
from app.services import page_service
from app.services.audit_service import write_audit_log


@dataclass(frozen=True)
class ValidationOutcome:
    #: Rule `message`s for every failed `ERROR` rule — any entry here blocks
    #: the write outright.
    blocking: list[str]
    #: Rule `message`s for every failed `WARNING` rule — the write proceeds,
    #: but `needs_review` is set and these are recorded on the audit entry.
    warnings: list[str]


def _available_names(columns: list[PageColumn]) -> frozenset[str]:
    return frozenset(c.key for c in columns)


async def list_active_rules(session: AsyncSession, page_id: uuid.UUID) -> list[PageValidation]:
    result = await session.execute(
        select(PageValidation)
        .where(PageValidation.page_id == page_id, PageValidation.is_active.is_(True))
        .order_by(PageValidation.created_at)
    )
    return list(result.scalars().all())


def evaluate(
    columns: list[PageColumn], rules: list[PageValidation], operands: dict[str, Any]
) -> ValidationOutcome:
    """`operands` is already Python-typed — `record_service.py`'s own
    validated write data merged with `formula_service.compute_typed_values`'s
    result, never wire-format text. A rule that can't evaluate (a config
    that outlived a column rename, say) is treated as passing rather than
    blocking a live write — `create_rule`/`update_rule` re-parsing the
    expression at save time is what should have caught that."""
    available = _available_names(columns)
    blocking: list[str] = []
    warnings: list[str] = []
    for rule in rules:
        try:
            parsed = parse_expression(rule.expression, available)
            result = evaluate_expression(parsed, operands)
        except (ExpressionSecurityError, FormulaEvaluationError):
            continue
        if result is True:
            continue
        if rule.severity == "ERROR":
            blocking.append(rule.message)
        else:
            warnings.append(rule.message)
    return ValidationOutcome(blocking=blocking, warnings=warnings)


async def _get_rule(
    session: AsyncSession, ctx: SecurityContext, rule_id: uuid.UUID
) -> tuple[PageValidation, Page]:
    result = await session.execute(
        select(PageValidation, Page)
        .join(Page, Page.id == PageValidation.page_id)
        .where(PageValidation.id == rule_id, Page.company_id == ctx.company_id)
    )
    row = result.one_or_none()
    if row is None:
        raise NotFoundError("No such validation rule.")
    return row[0], row[1]


async def create_rule(
    session: AsyncSession,
    ctx: SecurityContext,
    page: Page,
    columns: list[PageColumn],
    payload: ValidationRuleCreate,
) -> PageValidation:
    # Fail at save, never at read — the same principle every other schema
    # validation in this codebase already follows.
    parse_expression(payload.expression, _available_names(columns))
    rule = PageValidation(
        page_id=page.id,
        name=payload.name,
        expression=payload.expression,
        severity=payload.severity,
        message=payload.message,
    )
    session.add(rule)
    await session.flush()
    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="VALIDATION_CREATE",
        entity_type="page_validation",
        entity_id=rule.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        new_data={"name": rule.name, "expression": rule.expression, "severity": rule.severity},
    )
    return rule


async def update_rule(
    session: AsyncSession, ctx: SecurityContext, rule_id: uuid.UUID, payload: ValidationRuleUpdate
) -> PageValidation:
    rule, page = await _get_rule(session, ctx, rule_id)
    old_data = {
        "name": rule.name,
        "expression": rule.expression,
        "severity": rule.severity,
        "message": rule.message,
        "is_active": rule.is_active,
    }

    if payload.name is not None:
        rule.name = payload.name
    if payload.message is not None:
        rule.message = payload.message
    if payload.severity is not None:
        rule.severity = payload.severity
    if payload.is_active is not None:
        rule.is_active = payload.is_active
    if payload.expression is not None:
        columns = await page_service.get_page_columns(session, page.id)
        parse_expression(payload.expression, _available_names(columns))
        rule.expression = payload.expression

    await session.flush()
    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="VALIDATION_UPDATE",
        entity_type="page_validation",
        entity_id=rule.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        old_data=old_data,
        new_data={
            "name": rule.name,
            "expression": rule.expression,
            "severity": rule.severity,
            "message": rule.message,
            "is_active": rule.is_active,
        },
    )
    return rule


async def archive_rule(
    session: AsyncSession, ctx: SecurityContext, rule_id: uuid.UUID
) -> PageValidation:
    return await update_rule(session, ctx, rule_id, ValidationRuleUpdate(is_active=False))
