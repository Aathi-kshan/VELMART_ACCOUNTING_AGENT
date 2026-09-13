"""RLS-armed session for a route's own queries (plan section 20.2, step 2.6).

`set_config(..., true)` is transaction-scoped — it reverts the moment a
transaction commits or rolls back. `security_context()` (app/dependencies/auth.py)
already opened and closed one short transaction just to decode the token and
validate the user; by the time a route handler runs, that arming is gone.

This dependency opens the transaction a route's own business-logic queries
actually run in, and arms it again from the already-validated context — no
re-decoding, no re-querying `users`, just one cheap `set_config` call at the
start of this transaction. Every future router that touches a tenant table
depends on this rather than the raw `get_session`, so "RLS is always armed"
holds for every transaction, not just the first one per request.

`get_ai_reader_session` is the same idea over the `ai_reader` role instead of
`app_user` (plan section 16.5): `ai_reader` is granted SELECT only and cannot
see `users`/`refresh_tokens`/`idempotency_keys`, but it is **not** `BYPASSRLS`
— only `migrator` is — so a session opened against it still needs RLS armed
per-transaction exactly like `get_rls_session`, or every tenant query on it
would silently return zero rows. AI tool calls must depend on this, never on
`get_rls_session` or the raw `get_readonly_session`, so a bug in the AI layer
can be read-only and tenant-scoped by construction, not by care.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.db.readonly import get_readonly_session
from app.db.rls import set_rls_context
from app.db.session import get_session
from app.dependencies.auth import security_context


async def get_rls_session(
    ctx: SecurityContext = Depends(security_context),
    session: AsyncSession = Depends(get_session),
) -> AsyncIterator[AsyncSession]:
    async with session.begin():
        await set_rls_context(
            session, company_id=ctx.company_id, role=ctx.role.value, store_ids=ctx.store_ids
        )
        yield session


async def get_ai_reader_session(
    ctx: SecurityContext = Depends(security_context),
    session: AsyncSession = Depends(get_readonly_session),
) -> AsyncIterator[AsyncSession]:
    async with session.begin():
        await set_rls_context(
            session, company_id=ctx.company_id, role=ctx.role.value, store_ids=ctx.store_ids
        )
        yield session
