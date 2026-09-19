"""The shared audit-log writer (plan sections 18, 20.2).

Every mutation — and every permission denial — that matters gets exactly one
row here. Previously duplicated as a private helper inside `auth_service.py`;
extracted so `require_owner` (app/dependencies/guards.py) can write
`PERMISSION_DENIED` entries through the same path rather than a second,
independently-maintained copy of "write a row into a hash-chained,
RLS-scoped audit table."

Self-contained: arms RLS and ensures a transaction is open itself, so it works
correctly regardless of what the caller has already done on this session.
This matters concretely for two different call sites with different starting
states — `auth_service.py`'s login/refresh have already queried something
(so a transaction is already open via SQLAlchemy's autobegin), while
`require_owner` may be the first thing to touch its session at all.

`row_hash` is computed by the database trigger (migration
0005_audit_trigger_hashchain), never here — writing it here would defeat the
whole point of the chain.

`page_id` (P5, plan section 18.3): every call site that has a page in scope
should pass it — it's what the audit read API (`app/services/
audit_read_service.py`) filters "by page" on. `NULL` is correct for events
with no page (login, user/store management, a permission denial with no
page in scope yet).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import set_rls_context

_INSERT_AUDIT_LOG = text(
    """
    INSERT INTO audit_logs
        (company_id, actor_user_id, actor_role, action, entity_type,
         entity_id, page_id, old_data, new_data, source, ai_session_id,
         ip_address, user_agent, row_hash)
    VALUES
        (:company_id, :actor_user_id, CAST(:actor_role AS user_role), :action,
         :entity_type, :entity_id, :page_id, CAST(:old_data AS jsonb), CAST(:new_data AS jsonb),
         :source, :ai_session_id, CAST(:ip AS inet), :ua, '')
    """
)


async def write_audit_log(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    action: str,
    entity_type: str,
    actor_user_id: uuid.UUID | None,
    actor_role: str | None,
    entity_id: uuid.UUID | None = None,
    page_id: uuid.UUID | None = None,
    old_data: dict[str, Any] | None = None,
    new_data: dict[str, Any] | None = None,
    source: str = "APP",
    ai_session_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    params = {
        "company_id": str(company_id),
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "actor_role": actor_role,
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "page_id": str(page_id) if page_id else None,
        "old_data": json.dumps(old_data) if old_data is not None else None,
        "new_data": json.dumps(new_data) if new_data is not None else None,
        "source": source,
        "ai_session_id": str(ai_session_id) if ai_session_id else None,
        "ip": ip_address,
        "ua": user_agent,
    }

    if session.in_transaction():
        # The caller already armed this transaction's RLS context — writing
        # audit rows is never the first thing a request does. Re-arming here
        # actively broke it: `set_rls_context` rewrites all three settings, so
        # passing no `store_ids` cleared `app.store_ids` for the rest of the
        # caller's transaction and every later query lost its store scoping.
        # The old `role=actor_role or "OWNER"` fallback was worse — a caller
        # that omitted `actor_role` silently raised the transaction's RLS role
        # to OWNER. `audit_logs` carries `tenant_isolation` only (migration
        # 0006), so the role was never needed for this insert in any case.
        await session.execute(_INSERT_AUDIT_LOG, params)
        return

    # A session with no transaction of its own (the raw `get_session` that
    # `require_owner` uses): open one and arm it. It ends at the commit
    # below, so nothing set here outlives this function.
    async with session.begin():
        await set_rls_context(session, company_id=company_id, role=actor_role or "MANAGER")
        await session.execute(_INSERT_AUDIT_LOG, params)
