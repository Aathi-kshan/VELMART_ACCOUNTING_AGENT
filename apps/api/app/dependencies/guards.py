"""Permission guards (plan sections 4.2, 4.3).

`require_owner` is the FastAPI dependency every owner-only endpoint in
`app/core/permissions.py` (rows marked OWNER_ONLY) declares. It writes a
`PERMISSION_DENIED` audit entry *before* raising — plan section 18.2 lists
"repeated denials" as a signal worth having a permanent record of, and
following the commit-before-raise pattern `auth_service.py` established in
P1 is what makes that record survive regardless of what the caller does with
the exception afterward.

`require_page_access` now has real callers (P3's page/record routers).
Built in P2 with no caller yet, it originally treated "no grant" and "grant
lacks this specific permission" as the same flat 403 — but docs/API.md
section 1.4 is explicit that a manager without a page grant must get **404**,
not 403: confirming the page exists to someone who cannot see it is the same
leak P2 already closed for `update_user`'s "wrong company" case. So the two
cases are now split. There's no `Depends(...)`-usable factory version, in the
end: every P3 route that has `page_id` as a path parameter also needs the
`Page` row itself (for `projection_map`, `date_column_key`, ...), so they all
call `page_service.get_page_for_ctx` directly (which does this same check
internally) rather than a separate dependency that would just re-fetch
`page_access` a second time for no benefit.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Literal

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.logging import get_logger
from app.db.session import get_sessionmaker
from app.dependencies.auth import security_context
from app.services.audit_service import write_audit_log

log = get_logger(__name__)

#: A denial audit may wait this long for a connection before giving up. The
#: request is already refusing; holding a pool slot to record that is not
#: worth blocking other requests for.
_AUDIT_TIMEOUT_SECONDS = 5.0


async def _audit_denial(ctx: SecurityContext, **fields: object) -> None:
    """Record a permission denial on its own connection.

    The record has to survive the exception raised immediately afterwards,
    and it used to be made durable by calling `session.commit()` on the
    caller's own session. That worked, but it committed whatever else the
    request had already written — turning a refusal into a partial save —
    and it ended the transaction that `get_rls_session` was still holding
    open, discarding the transaction-scoped RLS settings with it.

    A separate short-lived session commits the audit row on its own and
    leaves the request's transaction untouched, free to roll back exactly as
    a failed request should.

    Two things this has to get right, both found by re-auditing the first
    version of this function:

    **It must not fail the request.** The caller is already refusing with a
    403 or 404. If the audit write raises — a full pool, a lock, anything —
    letting that propagate replaces a clean refusal with a 500, which is both
    a worse answer and a way to turn a permission probe into a denial of
    service. The denial is logged instead, so a lost audit row is visible
    rather than silent.

    **It must not exhaust the pool.** The request already holds a connection
    for its own transaction, so a denial needs a second one concurrently.
    With `DB_POOL_SIZE + DB_MAX_OVERFLOW` connections available, enough
    simultaneous denials could take every slot while each waits for another —
    exactly the flood a permission-denial burst produces. `_AUDIT_TIMEOUT`
    bounds the wait so a denial gives up and logs rather than holding a slot.
    """
    try:
        # Deliberately not wrapped in `audit_session.begin()`: with no
        # transaction open, `write_audit_log` opens one itself, arms the RLS
        # context this fresh connection does not yet have, and commits on exit.
        async with asyncio.timeout(_AUDIT_TIMEOUT_SECONDS):
            async with get_sessionmaker()() as audit_session:
                await write_audit_log(
                    audit_session,
                    company_id=ctx.company_id,
                    actor_user_id=ctx.user_id,
                    actor_role=ctx.role.value,
                    **fields,  # type: ignore[arg-type]
                )
    except Exception:
        # Never re-raise: the caller's 403/404 is the correct response and
        # must not become a 500 because the audit could not be written.
        log.exception(
            "audit.denial_write_failed",
            company_id=str(ctx.company_id),
            user_id=str(ctx.user_id),
            action=fields.get("action"),
        )


async def require_owner(
    ctx: SecurityContext = Depends(security_context),
) -> SecurityContext:
    """403 if the caller is not an OWNER. Every denial is audited."""
    if ctx.is_owner:
        return ctx

    await _audit_denial(ctx, action="PERMISSION_DENIED", entity_type="user", entity_id=ctx.user_id)
    raise PermissionDeniedError("This action is restricted to the Owner.")


async def require_page_access(
    page_id: uuid.UUID,
    need: Literal["view", "create"],
    ctx: SecurityContext,
    session: AsyncSession,
) -> None:
    """404 if the page is invisible to the caller; 403 if it's visible but
    `need` isn't granted. Owners implicitly have every page (plan section 4.3).

    Two different denials, on purpose (docs/API.md section 1.4): no grant row
    at all means this manager should not be able to confirm the page even
    exists, so that's 404, same as a genuinely missing page_id. A grant row
    that exists but doesn't cover `need` (e.g. view-only, asking to create)
    means the page is already known to be real to this caller, so 403 is
    honest rather than a leak.

    Called directly wherever a page (or the record's own `page_id`) is
    already in hand — `page_service.get_page_for_ctx` for path-param routes,
    or inline in `record_service` for `GET /records/{id}`, where `page_id`
    isn't known until the record itself is fetched.
    """
    if ctx.is_owner:
        return

    result = await session.execute(
        text(
            "SELECT can_view, can_create FROM page_access "
            "WHERE page_id = :page_id AND user_id = :user_id"
        ),
        {"page_id": str(page_id), "user_id": str(ctx.user_id)},
    )
    row = result.mappings().one_or_none()
    granted = row is not None and (row["can_view"] if need == "view" else row["can_create"])

    if granted:
        return

    # Both denial shapes are worth a permanent record (plan section 18.2) even
    # though they return different status codes to the caller — the audit
    # trail is owner-only, so recording "someone tried" here leaks nothing.
    await _audit_denial(
        ctx,
        action="PERMISSION_DENIED",
        entity_type="page",
        entity_id=page_id,
        page_id=page_id,
    )
    if row is None:
        raise NotFoundError("No such page.")
    raise PermissionDeniedError(f"You do not have {need} access to this page.")
