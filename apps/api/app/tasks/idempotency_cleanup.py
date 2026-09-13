"""Nightly idempotency-key cleanup (plan section 8.2, P5).

A thin wrapper — `app/core/idempotency.py`'s `purge_expired` already does
the real work. `idempotency_keys` carries no `company_id` and has no RLS
policy (`alembic/versions/0006_rls_policies.py`'s own comment excludes it
explicitly), so this runs on the plain `app_user` connection, not the
`migrator` (BYPASSRLS) one `audit_chain_verify.py` needs — there is no
cross-tenant read happening here to justify it.
"""

from __future__ import annotations

from app.core.idempotency import purge_expired
from app.db.session import get_sessionmaker


async def run() -> int:
    async with get_sessionmaker()() as session:
        deleted = await purge_expired(session)
        await session.commit()
        return deleted
