"""Column management (plan sections 8.3, 10.2, 10.3, 21.2). Owner only.

A `PageColumn` has no `company_id` of its own (migration 0002) — it's reached
through its page, which does. `_get_column_and_page` is the one small
addition `app/repositories/base.py`'s docstring already anticipated needing
for exactly this shape.

Like `page_service.py`, nothing here commits — callers use `get_rls_session`.
"""

from __future__ import annotations

import json
import uuid

from pydantic import ValidationError
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.errors import (
    ColumnKeyImmutableError,
    ConflictError,
    NotFoundError,
    SystemPageImmutableError,
    ValidationFailedError,
)
from app.models.page import Page
from app.models.page_column import ColumnType, PageColumn
from app.repositories.base import get_for_company
from app.schemas.column import ColumnDefinition, NarrowDryRunResult, UpdateColumnRequest
from app.schemas.dynamic import build_record_model
from app.services import formula_service
from app.services.audit_service import write_audit_log
from app.services.page_service import (
    allocate_projection_slot,
    derive_key,
    get_page_columns,
    validate_column_config,
)

#: Any type change into one of these is treated as safe/free widening — a
#: conservative rule (only same-type and "convert to TEXT" are free; every
#: other change, including ones that might genuinely be lossless, requires
#: confirm_narrow) rather than trying to model every pairwise type relationship.
_FREE_WIDEN_TARGETS = frozenset({ColumnType.TEXT, ColumnType.LONG_TEXT})

_INDEXABLE = frozenset(
    {ColumnType.NUMBER, ColumnType.CURRENCY, ColumnType.DATE, ColumnType.DATETIME}
)


def _is_free_widen(old_type: ColumnType, new_type: ColumnType) -> bool:
    return old_type == new_type or new_type in _FREE_WIDEN_TARGETS


async def _column_key_collides(session: AsyncSession, page_id: uuid.UUID, key: str) -> bool:
    result = await session.execute(
        select(PageColumn.id).where(PageColumn.page_id == page_id, PageColumn.key == key)
    )
    return result.scalar_one_or_none() is not None


async def _get_column_and_page(
    session: AsyncSession, ctx: SecurityContext, column_id: uuid.UUID
) -> tuple[PageColumn, Page]:
    result = await session.execute(
        select(PageColumn, Page)
        .join(Page, Page.id == PageColumn.page_id)
        .where(PageColumn.id == column_id, Page.company_id == ctx.company_id)
    )
    row = result.one_or_none()
    if row is None:
        raise NotFoundError("No such column.")
    return row[0], row[1]


async def _count_option_usage(
    session: AsyncSession, *, page_id: uuid.UUID, column: PageColumn, options: set[str]
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for option in options:
        if column.data_type == ColumnType.MULTI_SELECT:
            result = await session.execute(
                text(
                    "SELECT count(*) FROM records WHERE page_id = :page_id "
                    "AND is_deleted = false AND data -> :key @> CAST(:value AS jsonb)"
                ),
                {"page_id": str(page_id), "key": column.key, "value": json.dumps([option])},
            )
        else:
            result = await session.execute(
                text(
                    "SELECT count(*) FROM records WHERE page_id = :page_id "
                    "AND is_deleted = false AND data ->> :key = :value"
                ),
                {"page_id": str(page_id), "key": column.key, "value": option},
            )
        count = result.scalar_one()
        if count:
            counts[option] = count
    return counts


async def add_column(
    session: AsyncSession, ctx: SecurityContext, page_id: uuid.UUID, payload: ColumnDefinition
) -> PageColumn:
    page = await get_for_company(session, Page, page_id, ctx.company_id)
    if page is None:
        raise NotFoundError("No such page.")
    if page.is_system:
        raise SystemPageImmutableError(
            "System pages cannot have columns added; their schema changes only by migration."
        )

    key = derive_key(payload.name)
    if await _column_key_collides(session, page.id, key):
        raise ConflictError(f"A column named '{payload.name}' already exists on this page.")
    await validate_column_config(
        session, ctx.company_id, payload.data_type, payload.config, self_page_key=page.key
    )

    max_position_result = await session.execute(
        select(func.max(PageColumn.position)).where(PageColumn.page_id == page.id)
    )
    next_position = (max_position_result.scalar_one_or_none() or -1) + 1

    column = PageColumn(
        page_id=page.id,
        key=key,
        name=payload.name,
        data_type=payload.data_type,
        position=next_position,
        is_required=payload.is_required,
        is_indexed=payload.is_indexed,
        is_protected=payload.is_protected,
        config=payload.config,
        description=payload.description,
    )

    if column.data_type is ColumnType.FORMULA:
        existing = await get_page_columns(session, page.id)
        formula_service.validate_formula_column(column, [*existing, column])

    session.add(column)
    await session.flush()

    if column.is_indexed and column.data_type in _INDEXABLE:
        projection_map = dict(page.projection_map)
        projection_map[column.key] = allocate_projection_slot(column.data_type, projection_map)
        page.projection_map = projection_map

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="COLUMN_CREATE",
        entity_type="page_column",
        entity_id=column.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        new_data={"key": column.key, "name": column.name, "data_type": column.data_type.value},
    )
    return column


async def update_column(
    session: AsyncSession, ctx: SecurityContext, column_id: uuid.UUID, payload: UpdateColumnRequest
) -> tuple[PageColumn, dict[str, int]]:
    """Returns the updated column plus any SELECT/MULTI_SELECT options that
    were removed while still in use on existing records (a warning, not a
    block — plan section 10.3)."""
    column, page = await _get_column_and_page(session, ctx, column_id)
    if page.is_system:
        raise SystemPageImmutableError(
            "System page columns cannot be edited; their schema changes only by migration."
        )
    if payload.key is not None and payload.key != column.key:
        raise ColumnKeyImmutableError("A column's key cannot be changed once created.")

    old_data = {
        "name": column.name,
        "data_type": column.data_type.value,
        "is_required": column.is_required,
        "is_indexed": column.is_indexed,
        "is_protected": column.is_protected,
        "config": column.config,
        "is_archived": column.is_archived,
    }
    values: dict[str, object] = {}
    removed_options_in_use: dict[str, int] = {}

    if payload.name is not None:
        values["name"] = payload.name
    if payload.position is not None:
        values["position"] = payload.position
    if payload.description is not None:
        values["description"] = payload.description
    if payload.is_required is not None:
        values["is_required"] = payload.is_required
    if payload.is_protected is not None:
        values["is_protected"] = payload.is_protected
    if payload.is_archived is not None:
        values["is_archived"] = payload.is_archived

    effective_type = payload.data_type or column.data_type

    if payload.config is not None:
        await validate_column_config(
            session, ctx.company_id, effective_type, payload.config, self_page_key=page.key
        )
        if column.data_type in (ColumnType.SELECT, ColumnType.MULTI_SELECT):
            old_options = set(column.config.get("options") or [])
            new_options = set(payload.config.get("options") or [])
            removed = old_options - new_options
            if removed:
                removed_options_in_use = await _count_option_usage(
                    session, page_id=page.id, column=column, options=removed
                )
        values["config"] = payload.config

    if payload.data_type is not None and payload.data_type != column.data_type:
        if not _is_free_widen(column.data_type, payload.data_type) and not payload.confirm_narrow:
            raise ValidationFailedError(
                "Narrowing a column's type requires confirm_narrow=true — call "
                "POST /columns/{id}/narrow-dry-run first to see what would fail."
            )
        values["data_type"] = payload.data_type

    if effective_type is ColumnType.FORMULA and (
        payload.data_type is not None or payload.config is not None
    ):
        # Re-validate against the *post-update* state before anything is
        # written — same "fail at save, never at read" principle as
        # everything else in this module. Built from the other columns'
        # current state plus this one's candidate state, not yet persisted.
        existing = await get_page_columns(session, page.id)
        others = [c for c in existing if c.id != column.id]
        candidate = PageColumn(
            id=column.id,
            key=column.key,
            name=payload.name if payload.name is not None else column.name,
            data_type=effective_type,
            position=column.position,
            is_required=column.is_required,
            is_indexed=column.is_indexed,
            is_protected=column.is_protected,
            config=payload.config if payload.config is not None else column.config,
            description=column.description,
            is_archived=column.is_archived,
        )
        formula_service.validate_formula_column(candidate, [*others, candidate])

    if payload.is_indexed is not None and payload.is_indexed != column.is_indexed:
        projection_map = dict(page.projection_map)
        if payload.is_indexed:
            if effective_type not in _INDEXABLE:
                raise ValidationFailedError(f"{effective_type.value} columns cannot be indexed.")
            projection_map[column.key] = allocate_projection_slot(effective_type, projection_map)
        else:
            projection_map.pop(column.key, None)
        page.projection_map = projection_map
        values["is_indexed"] = payload.is_indexed

    if values:
        await session.execute(update(PageColumn).where(PageColumn.id == column.id).values(**values))
        await session.refresh(column)

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="COLUMN_UPDATE",
        entity_type="page_column",
        entity_id=column.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        old_data=old_data,
        new_data={
            "name": column.name,
            "data_type": column.data_type.value,
            "is_required": column.is_required,
            "is_indexed": column.is_indexed,
            "is_protected": column.is_protected,
            "config": column.config,
            "is_archived": column.is_archived,
        },
    )
    return column, removed_options_in_use


async def narrow_dry_run(
    session: AsyncSession, ctx: SecurityContext, column_id: uuid.UUID, new_type: ColumnType
) -> NarrowDryRunResult:
    """Scans every existing value for this column under the *proposed* type
    and reports how many would fail — informational only, never mutates or
    deletes anything (plan section 10.3)."""
    column, page = await _get_column_and_page(session, ctx, column_id)

    result = await session.execute(
        text(
            "SELECT id, data ->> :key AS value FROM records "
            "WHERE page_id = :page_id AND is_deleted = false AND data ->> :key IS NOT NULL"
        ),
        {"key": column.key, "page_id": str(page.id)},
    )
    rows = result.mappings().all()

    probe_column = PageColumn(
        key=column.key,
        name=column.name,
        data_type=new_type,
        position=0,
        is_required=False,
        is_indexed=False,
        is_protected=False,
        config=column.config,
        description=None,
        is_archived=False,
    )
    model = build_record_model([probe_column], partial=True, model_name="NarrowProbe")

    would_fail = 0
    sample_failures: list[dict[str, object]] = []
    for row in rows:
        try:
            model(**{column.key: row["value"]})
        except ValidationError as exc:
            would_fail += 1
            if len(sample_failures) < 10:
                sample_failures.append(
                    {"record_id": str(row["id"]), "value": row["value"], "error": str(exc)}
                )
    return NarrowDryRunResult(would_fail=would_fail, sample_failures=sample_failures)
