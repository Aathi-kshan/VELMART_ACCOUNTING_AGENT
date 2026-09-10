"""Set the RLS context the migration 0006 policies read.

The policies compare against three settings:

    app.company_id   -> tenant_isolation on every tenant table
    app.role         -> store_scope (OWNER sees every store)
    app.store_ids    -> store_scope (comma-separated UUIDs)

`set_config(name, value, true)` is used rather than `SET LOCAL`, because
`SET LOCAL` cannot take a bind parameter — building it by string formatting
would put caller-supplied values straight into SQL. `set_config(..., true)` is
transaction-scoped and does exactly the same job safely.

Must be called inside an open transaction; outside one the settings are
discarded immediately and every tenant query silently returns nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SET_RLS = text(
    """
    SELECT set_config('app.company_id', :company_id, true),
           set_config('app.role',       :role,       true),
           set_config('app.store_ids',  :store_ids,  true)
    """
)


async def set_rls_context(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    role: str,
    store_ids: Sequence[uuid.UUID] = (),
) -> None:
    """Bind the tenant context for the remainder of the current transaction."""
    if not session.in_transaction():
        raise RuntimeError(
            "set_rls_context must be called inside a transaction; outside one the "
            "settings are discarded and RLS will filter every row away."
        )
    await session.execute(
        _SET_RLS,
        {
            "company_id": str(company_id),
            "role": role,
            "store_ids": ",".join(str(s) for s in store_ids),
        },
    )
