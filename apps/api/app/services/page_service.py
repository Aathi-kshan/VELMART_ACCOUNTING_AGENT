"""Page management (plan sections 8.3, 10.1, 10.3, 21.2). Create/edit/archive
are Owner-only; `list_pages`/`get_page_schema` are the 🟡 filtered case — a
manager sees only pages they're granted (plan section 4.3).

Like `user_service.py`/`store_service.py` (P2), nothing here commits: every
caller is a router using `get_rls_session`, which owns one transaction for
the whole request.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Literal

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.errors import (
    ConflictError,
    NotFoundError,
    ReservedPageKeyError,
    SystemPageImmutableError,
    ValidationFailedError,
    VersionConflictError,
)
from app.dependencies.guards import require_page_access
from app.models.business import RESERVED_PAGE_KEYS
from app.models.page import Page, PageKind
from app.models.page_access import PageAccess
from app.models.page_column import ColumnType, PageColumn
from app.models.user import User, UserRole
from app.repositories.base import get_for_company
from app.schemas.page import CreatePageRequest, UpdatePageRequest
from app.services import formula_service
from app.services.audit_service import write_audit_log

_SLUG_RE = re.compile(r"[^a-z0-9]+")

#: The projection columns `records` carries (migration 0002) — shared across
#: every indexed NUMBER/CURRENCY/DATE/DATETIME column on one page.
NUMERIC_PROJECTION_SLOTS = ("num_1", "num_2", "num_3", "num_4")
DATE_PROJECTION_SLOTS = ("date_1", "date_2")


def derive_key(name: str) -> str:
    """The stable slug used everywhere a page/column is referred to by key
    (plan section 10.1) — lowercase, non-alphanumeric runs collapsed to `_`.
    Deterministic and one-way: a client can predict it, but it never changes
    once assigned (plan section 10.3)."""
    slug = _SLUG_RE.sub("_", name.strip().lower()).strip("_")
    if not slug:
        raise ValidationFailedError("Name must contain at least one letter or digit.")
    return slug


def allocate_projection_slot(data_type: ColumnType, projection_map: dict[str, str]) -> str:
    """The next free `num_N`/`date_N` slot for an indexed column, given the
    page's current `projection_map`. Raises rather than silently leaving the
    column un-indexed — a column whose metadata says `is_indexed=true` but
    has no real projection would be lying about itself."""
    is_numeric = data_type in (ColumnType.NUMBER, ColumnType.CURRENCY)
    slots = NUMERIC_PROJECTION_SLOTS if is_numeric else DATE_PROJECTION_SLOTS
    used = set(projection_map.values())
    for slot in slots:
        if slot not in used:
            return slot
    kind = "numeric" if is_numeric else "date"
    raise ConflictError(
        f"This page already has the maximum of {len(slots)} indexed {kind} columns."
    )


async def validate_column_config(
    session: AsyncSession,
    company_id: uuid.UUID,
    data_type: ColumnType,
    config: dict[str, object],
    *,
    self_page_key: str | None = None,
) -> None:
    if data_type is ColumnType.RECORD_REF:
        target_page_key = config.get("target_page_key")
        if not isinstance(target_page_key, str) or not target_page_key:
            raise ValidationFailedError(
                "RECORD_REF columns require a 'target_page_key' naming a real page."
            )
        # A page referencing itself (e.g. an employee's "reports to" column)
        # can't be looked up yet during that same page's own creation — the
        # row doesn't exist until this call returns. Skip existence/
        # display-column checks in that one case; every other target must be
        # a real, non-archived page in this company (fail at save, never at
        # read — the same principle every other schema validation follows).
        if target_page_key != self_page_key:
            target_page = await get_page_by_key(session, company_id, target_page_key)
            if target_page is None or target_page.is_archived:
                raise ValidationFailedError(
                    f"'{target_page_key}' is not a real page in this company."
                )
            display_column = config.get("display_column")
            if display_column is not None:
                if not isinstance(display_column, str):
                    raise ValidationFailedError("'display_column' must be a column key string.")
                target_columns = await get_page_columns(session, target_page.id)
                if not any(c.key == display_column for c in target_columns):
                    raise ValidationFailedError(
                        f"'{display_column}' is not a real column on page '{target_page_key}'."
                    )
        return

    if data_type in (ColumnType.SELECT, ColumnType.MULTI_SELECT):
        options = config.get("options")
        if (
            not isinstance(options, list)
            or not options
            or not all(isinstance(o, str) and o for o in options)
        ):
            raise ValidationFailedError(
                "SELECT/MULTI_SELECT columns require a non-empty 'options' list of strings."
            )
        default = config.get("default")
        if default is not None:
            # A default outside the option list would never be caught at
            # write time (a pydantic `Field(default=...)` is never itself
            # re-validated — plan section 3.4's own "fail at save, not at
            # read" principle applies just as much to the default a client
            # never even supplies).
            if data_type is ColumnType.MULTI_SELECT:
                if not isinstance(default, list) or not all(d in options for d in default):
                    raise ValidationFailedError(
                        "A MULTI_SELECT column's 'default' must be a list drawn from its "
                        "own 'options'."
                    )
            elif default not in options:
                raise ValidationFailedError(
                    f"A SELECT column's 'default' ({default!r}) must be one of its own "
                    "'options'."
                )


def _resolve_special_key(
    value: str | None,
    columns: list[PageColumn],
    allowed_types: set[ColumnType],
    field_name: str,
) -> str | None:
    if value is None:
        return None
    valid = {c.key: c.data_type for c in columns}
    if value not in valid or valid[value] not in allowed_types:
        candidates = sorted(k for k, t in valid.items() if t in allowed_types)
        raise ValidationFailedError(
            f"{field_name} must be one of this page's columns of the right type. "
            f"Candidates: {candidates}"
        )
    return value


async def _key_collides(session: AsyncSession, company_id: uuid.UUID, key: str) -> bool:
    result = await session.execute(
        select(Page.id).where(Page.company_id == company_id, Page.key == key)
    )
    return result.scalar_one_or_none() is not None


async def create_page(
    session: AsyncSession, ctx: SecurityContext, payload: CreatePageRequest
) -> Page:
    key = derive_key(payload.name)
    if key in RESERVED_PAGE_KEYS:
        raise ReservedPageKeyError(f"'{payload.name}' is a reserved page name.")
    if await _key_collides(session, ctx.company_id, key):
        raise ConflictError(f"A page named '{payload.name}' already exists.")

    columns: list[PageColumn] = []
    seen_keys: set[str] = set()
    for position, col_def in enumerate(payload.columns):
        col_key = derive_key(col_def.name)
        if col_key in seen_keys:
            raise ValidationFailedError(
                f"Column '{col_def.name}' derives a key that collides with another column."
            )
        seen_keys.add(col_key)
        await validate_column_config(
            session, ctx.company_id, col_def.data_type, col_def.config, self_page_key=key
        )
        columns.append(
            PageColumn(
                key=col_key,
                name=col_def.name,
                data_type=col_def.data_type,
                position=position,
                is_required=col_def.is_required,
                is_indexed=col_def.is_indexed,
                is_protected=col_def.is_protected,
                config=col_def.config,
                description=col_def.description,
            )
        )

    # FORMULA columns were validated only by `schema_service.add_column`/
    # `update_column`, so an expression supplied in this initial payload
    # skipped the whitelist parser entirely: a formula naming a column that
    # does not exist, or calling a function with the wrong number of
    # arguments, was accepted here and only failed later — silently blank on
    # read (`formula_service.prepare` swallows it) or as a 500 from inside a
    # filter/sort/aggregate once the SQL compiler indexed a missing argument.
    # Validate at save time, like every other column config above.
    for column in columns:
        if column.data_type is ColumnType.FORMULA:
            formula_service.validate_formula_column(column, columns)

    date_column_key = _resolve_special_key(
        payload.date_column_key, columns, {ColumnType.DATE, ColumnType.DATETIME}, "date_column_key"
    )
    store_column_key = _resolve_special_key(
        payload.store_column_key, columns, {ColumnType.STORE_REF}, "store_column_key"
    )
    balance_column_key = _resolve_special_key(
        payload.balance_column_key,
        columns,
        {ColumnType.NUMBER, ColumnType.CURRENCY},
        "balance_column_key",
    )

    page = Page(
        company_id=ctx.company_id,
        key=key,
        name=payload.name,
        description=payload.description,
        icon=payload.icon,
        kind=payload.kind,
        date_column_key=date_column_key,
        store_column_key=store_column_key,
        balance_column_key=balance_column_key,
        created_by=ctx.user_id,
    )
    session.add(page)
    await session.flush()  # assign page.id before columns reference it

    for column in columns:
        column.page_id = page.id
        session.add(column)
    await session.flush()

    projection_map: dict[str, str] = {}
    indexable = {ColumnType.NUMBER, ColumnType.CURRENCY, ColumnType.DATE, ColumnType.DATETIME}
    for column in columns:
        if column.is_indexed and column.data_type in indexable:
            projection_map[column.key] = allocate_projection_slot(
                column.data_type, projection_map
            )
    page.projection_map = projection_map

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="PAGE_CREATE",
        entity_type="page",
        entity_id=page.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        new_data={"key": page.key, "name": page.name, "kind": page.kind.value},
    )
    return page


async def list_pages(session: AsyncSession, ctx: SecurityContext) -> list[Page]:
    if ctx.is_owner:
        result = await session.execute(
            select(Page)
            .where(Page.company_id == ctx.company_id, Page.is_archived.is_(False))
            .order_by(Page.name)
        )
        return list(result.scalars().all())

    result = await session.execute(
        select(Page)
        .join(PageAccess, PageAccess.page_id == Page.id)
        .where(
            PageAccess.user_id == ctx.user_id,
            PageAccess.can_view.is_(True),
            Page.company_id == ctx.company_id,
            Page.is_archived.is_(False),
        )
        .order_by(Page.name)
    )
    return list(result.scalars().all())


async def get_page_for_ctx(
    session: AsyncSession,
    ctx: SecurityContext,
    page_id: uuid.UUID,
    *,
    need: Literal["view", "create"] = "view",
) -> Page:
    """Fetch one page, 404 if it doesn't exist in this company *or* (manager)
    isn't granted — the two cases are indistinguishable on purpose."""
    page = await get_for_company(session, Page, page_id, ctx.company_id)
    if page is None:
        raise NotFoundError("No such page.")
    if not ctx.is_owner:
        await require_page_access(page_id, need, ctx, session)
    return page


#: The six pages every company ships with (plan section 12). Every column's
#: `key` is chosen to equal its native table's real column name
#: (`app/models/business/`) — that's what lets `resolve_column`
#: (`app/repositories/records.py`) be a plain `getattr` for these pages,
#: with no projection bookkeeping (`is_indexed`/`projection_map`) needed:
#: indexing is already real. Each column tuple is
#: `(key, name, data_type, is_required, config, is_protected)`.
_SYSTEM_PAGES: tuple[dict[str, Any], ...] = (
    {
        "key": "employee_salary",
        "name": "Employee Salary",
        "storage_table": "employee_salaries",
        "date_column_key": "payment_date",
        "columns": (
            ("payment_date", "Payment Date", ColumnType.DATE, True, {}, False),
            ("employee_name", "Employee Name", ColumnType.TEXT, True, {}, False),
            ("paid_amount", "Paid Amount", ColumnType.CURRENCY, True, {}, False),
            ("reference", "Reference", ColumnType.TEXT, False, {}, False),
        ),
    },
    {
        "key": "purchases",
        "name": "Purchases for Cash",
        "storage_table": "purchases",
        "date_column_key": "purchase_date",
        "columns": (
            ("purchase_date", "Purchase Date", ColumnType.DATE, True, {}, False),
            # Not required: omitted at create time so Postgres's own
            # server_default (now()) applies, rather than the client having
            # to guess "when the entry was recorded" itself.
            ("entry_time", "Entry Time", ColumnType.DATETIME, False, {}, False),
            ("purchase_name", "Purchase Name", ColumnType.TEXT, True, {}, False),
            ("total_amount", "Total Amount", ColumnType.CURRENCY, True, {}, False),
        ),
    },
    {
        "key": "expenses",
        "name": "Expenses",
        "storage_table": "expenses",
        "date_column_key": "expense_date",
        "columns": (
            ("expense_date", "Expense Date", ColumnType.DATE, True, {}, False),
            ("entry_time", "Entry Time", ColumnType.DATETIME, False, {}, False),
            ("expense_name", "Expense Name", ColumnType.TEXT, True, {}, False),
            ("amount", "Amount", ColumnType.CURRENCY, True, {}, False),
            ("description", "Description", ColumnType.LONG_TEXT, False, {}, False),
        ),
    },
    {
        "key": "daily_revenue",
        "name": "Daily Revenue",
        "storage_table": "daily_revenue",
        "date_column_key": "entry_date",
        "columns": (
            ("entry_date", "Entry Date", ColumnType.DATE, True, {}, False),
            # Required, no config default: a `NUMBER`/`CURRENCY` column's
            # unvalidated pydantic default (`build_record_model`'s
            # `Field(default=...)`) is never coerced from its raw config
            # value — it would surface as a literal string, not a Decimal.
            # Requiring an explicit "0.00" sidesteps that rather than
            # relying on a default here.
            ("cash_sales", "Cash Sales", ColumnType.CURRENCY, True, {}, False),
            ("card_sales", "Card Sales", ColumnType.CURRENCY, True, {}, False),
            ("total_revenue", "Total Revenue", ColumnType.CURRENCY, False, {}, False),
        ),
    },
    {
        "key": "cash_ledger",
        "name": "Cash Ledger",
        "storage_table": "cash_ledger",
        "date_column_key": "entry_date",
        "columns": (
            ("entry_date", "Entry Date", ColumnType.DATE, True, {}, False),
            ("cash_amount", "Cash Amount", ColumnType.CURRENCY, True, {}, False),
            ("card_sales_amount", "Card Sales Amount", ColumnType.CURRENCY, True, {}, False),
            ("total_amount", "Total Amount", ColumnType.CURRENCY, False, {}, False),
        ),
    },
    {
        "key": "cheques",
        "name": "Cheques",
        "storage_table": "cheques",
        "date_column_key": "cheque_date",
        "columns": (
            ("cheque_number", "Cheque Number", ColumnType.TEXT, True, {}, False),
            ("payee_name", "Payee Name", ColumnType.TEXT, False, {}, False),
            ("amount", "Amount", ColumnType.CURRENCY, True, {}, False),
            ("cheque_date", "Cheque Date", ColumnType.DATE, False, {}, False),
            (
                "cheque_status",
                "Status",
                ColumnType.SELECT,
                False,
                {"options": ["PENDING", "PAID"], "default": "PENDING"},
                True,
            ),
            ("reference", "Reference", ColumnType.TEXT, False, {}, False),
        ),
    },
)


async def register_system_pages(
    session: AsyncSession, ctx: SecurityContext, company_id: uuid.UUID
) -> None:
    """Seeds the six system pages for one company (plan section 3.5's
    registration step) — idempotent, a key already present for this company
    is left untouched entirely, columns included. `generated_columns_for`
    (`app/repositories/records.py`) is what actually keeps `total_revenue`/
    `total_amount` out of write bodies, not anything set here; those two
    are ordinary, readable `CURRENCY` columns from this function's point of
    view. Every generic page-engine endpoint works over these exactly as it
    does an Owner-created page as soon as this has run once."""
    for definition in _SYSTEM_PAGES:
        exists = await session.execute(
            select(Page.id).where(Page.company_id == company_id, Page.key == definition["key"])
        )
        if exists.scalar_one_or_none() is not None:
            continue

        page = Page(
            company_id=company_id,
            key=definition["key"],
            name=definition["name"],
            kind=PageKind.REGISTER,
            date_column_key=definition["date_column_key"],
            is_system=True,
            storage_table=definition["storage_table"],
            created_by=ctx.user_id,
        )
        session.add(page)
        await session.flush()

        for position, (key, name, data_type, is_required, config, is_protected) in enumerate(
            definition["columns"]
        ):
            session.add(
                PageColumn(
                    page_id=page.id,
                    key=key,
                    name=name,
                    data_type=data_type,
                    position=position,
                    is_required=is_required,
                    is_protected=is_protected,
                    config=config,
                )
            )
        await session.flush()

        await write_audit_log(
            session,
            company_id=company_id,
            action="PAGE_CREATE",
            entity_type="page",
            entity_id=page.id,
            page_id=page.id,
            actor_user_id=ctx.user_id,
            actor_role=ctx.role.value,
            new_data={"key": page.key, "name": page.name, "is_system": True},
        )


async def get_page_by_key(session: AsyncSession, company_id: uuid.UUID, key: str) -> Page | None:
    result = await session.execute(
        select(Page).where(Page.company_id == company_id, Page.key == key)
    )
    return result.scalar_one_or_none()


async def list_system_pages(session: AsyncSession, company_id: uuid.UUID) -> list[Page]:
    """The six native-table pages for one company — `find_record`'s fallback
    list when a bare `record_id` isn't in the generic `records` table."""
    result = await session.execute(
        select(Page).where(Page.company_id == company_id, Page.is_system.is_(True))
    )
    return list(result.scalars().all())


async def get_page_columns(session: AsyncSession, page_id: uuid.UUID) -> list[PageColumn]:
    result = await session.execute(
        select(PageColumn)
        .where(PageColumn.page_id == page_id, PageColumn.is_archived.is_(False))
        .order_by(PageColumn.position)
    )
    return list(result.scalars().all())


async def get_page_schema(
    session: AsyncSession, ctx: SecurityContext, page_id: uuid.UUID
) -> tuple[Page, list[PageColumn]]:
    page = await get_page_for_ctx(session, ctx, page_id, need="view")
    columns = await get_page_columns(session, page.id)
    return page, columns


async def bump_schema_version(
    session: AsyncSession, page_id: uuid.UUID, *, expected_version: int | None = None
) -> int:
    """Advance a page's schema version, optionally under an `If-Match` check.

    `pages.version` has existed since 0002 and is returned on every
    `PageOut`/`PageSchemaOut`, but nothing ever wrote it — it stayed at 1 for
    the life of a page however often the page was renamed or its columns
    added, retyped or archived. Two things followed from that: a client
    caching a `PageSchema` had no way to notice it had gone stale, which
    matters precisely because this engine's promise is that an Owner changes
    a page's columns and clients pick it up with no app release; and the
    version being *present* implied an optimistic-locking check that did not
    exist, so `If-Match: 1` was accepted forever and two Owners restructuring
    a page at once silently overwrote each other.

    `expected_version` is optional on purpose. The Flutter client sends
    `If-Match` for records only (`page_repository.dart`), so requiring it on
    schema edits would break every existing caller. Supplying it opts into
    the check; omitting it bumps unconditionally.
    """
    stmt = update(Page).where(Page.id == page_id)
    if expected_version is not None:
        stmt = stmt.where(Page.version == expected_version)
    new_version = await session.scalar(
        stmt.values(version=Page.version + 1).returning(Page.version)
    )
    if new_version is None:
        current = await session.scalar(select(Page.version).where(Page.id == page_id))
        raise VersionConflictError(
            f"This page's structure has changed since version {expected_version}.",
            extra={"current_version": current} if current is not None else None,
        )
    return int(new_version)


async def update_page(
    session: AsyncSession,
    ctx: SecurityContext,
    page_id: uuid.UUID,
    payload: UpdatePageRequest,
    version: int | None = None,
) -> Page | None:
    """Returns None if not found in this company — router turns that into 404."""
    page = await get_for_company(session, Page, page_id, ctx.company_id)
    if page is None:
        return None
    if page.is_system:
        raise SystemPageImmutableError(
            "System pages cannot be edited; their schema changes only by migration."
        )

    old_data = {
        "name": page.name,
        "description": page.description,
        "icon": page.icon,
        "date_column_key": page.date_column_key,
        "store_column_key": page.store_column_key,
        "balance_column_key": page.balance_column_key,
    }
    values: dict[str, object] = {}
    if payload.name is not None:
        values["name"] = payload.name
    if payload.description is not None:
        values["description"] = payload.description
    if payload.icon is not None:
        values["icon"] = payload.icon

    if (
        payload.date_column_key is not None
        or payload.store_column_key is not None
        or payload.balance_column_key is not None
    ):
        columns = await get_page_columns(session, page.id)
        if payload.date_column_key is not None:
            values["date_column_key"] = _resolve_special_key(
                payload.date_column_key, columns, {ColumnType.DATE, ColumnType.DATETIME},
                "date_column_key",
            )
        if payload.store_column_key is not None:
            values["store_column_key"] = _resolve_special_key(
                payload.store_column_key, columns, {ColumnType.STORE_REF}, "store_column_key"
            )
        if payload.balance_column_key is not None:
            values["balance_column_key"] = _resolve_special_key(
                payload.balance_column_key,
                columns,
                {ColumnType.NUMBER, ColumnType.CURRENCY},
                "balance_column_key",
            )

    if values:
        await session.execute(update(Page).where(Page.id == page.id).values(**values))

    # Bumped even when `values` is empty but a version was asserted, so an
    # `If-Match` that is already stale is still reported rather than silently
    # succeeding as a no-op.
    if values or version is not None:
        await bump_schema_version(session, page.id, expected_version=version)
    await session.refresh(page)

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="PAGE_UPDATE",
        entity_type="page",
        entity_id=page.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        old_data=old_data,
        new_data={
            "name": page.name,
            "description": page.description,
            "icon": page.icon,
            "date_column_key": page.date_column_key,
            "store_column_key": page.store_column_key,
            "balance_column_key": page.balance_column_key,
        },
    )
    return page


async def archive_page(
    session: AsyncSession, ctx: SecurityContext, page_id: uuid.UUID
) -> Page | None:
    """Soft archive (plan section 10.3: hard delete is a later, explicit,
    export-gated step — not built in P3)."""
    page = await get_for_company(session, Page, page_id, ctx.company_id)
    if page is None:
        return None
    if page.is_system:
        raise SystemPageImmutableError(
            "System pages cannot be deleted; their schema changes only by migration."
        )

    await session.execute(update(Page).where(Page.id == page.id).values(is_archived=True))
    await session.refresh(page)
    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="PAGE_ARCHIVE",
        entity_type="page",
        entity_id=page.id,
        page_id=page.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
    )
    return page


async def get_page_access(
    session: AsyncSession, ctx: SecurityContext, page_id: uuid.UUID
) -> list[PageAccess]:
    """Read-back for the Owner's access editor — without this the client has
    no way to know what's currently granted before it overwrites it with a
    wholesale `PUT` (the bug that made grants look like they weren't
    saving: the editor opened blank every time)."""
    page = await get_for_company(session, Page, page_id, ctx.company_id)
    if page is None:
        raise NotFoundError("No such page.")
    result = await session.execute(select(PageAccess).where(PageAccess.page_id == page_id))
    return list(result.scalars().all())


async def set_page_access(
    session: AsyncSession, ctx: SecurityContext, page_id: uuid.UUID, grants: list[dict[str, object]]
) -> list[PageAccess]:
    """Wholesale replace (plan section 21.2 `PUT`) — mirrors P2's
    `user_service._set_store_assignments`: a page with no grant is invisible
    to every manager (default-deny, plan section 4.3)."""
    page = await get_for_company(session, Page, page_id, ctx.company_id)
    if page is None:
        raise NotFoundError("No such page.")

    if grants:
        user_ids = [g["user_id"] for g in grants]
        result = await session.execute(
            select(User.id, User.role).where(
                User.id.in_(user_ids), User.company_id == ctx.company_id
            )
        )
        found = {row.id: row.role for row in result.all()}
        missing = set(user_ids) - found.keys()
        if missing:
            raise ValidationFailedError("One or more users do not exist in this company.")
        non_managers = [uid for uid, role in found.items() if role != UserRole.MANAGER]
        if non_managers:
            raise ValidationFailedError(
                "Page access can only be granted to managers — an owner already has full access."
            )

    await session.execute(delete(PageAccess).where(PageAccess.page_id == page_id))
    rows = [
        PageAccess(
            page_id=page_id,
            user_id=g["user_id"],
            can_view=g.get("can_view", True),
            can_create=g.get("can_create", True),
        )
        for g in grants
    ]
    session.add_all(rows)
    await session.flush()

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="PAGE_ACCESS_UPDATE",
        entity_type="page",
        entity_id=page_id,
        page_id=page_id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        new_data={"grants": [{"user_id": str(g["user_id"])} for g in grants]},
    )
    return rows
