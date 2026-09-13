"""Nightly audit hash-chain verification (plan section 18.1, P5).

Walks `audit_logs` in true global `id` order (the chain is one sequence
across every company — the trigger itself has no `WHERE company_id`, see
migration 0005) and recomputes each row's expected hash with the *exact
same* `concat_ws('|', ...)` + `digest(..., 'sha256')` formula the
`fn_audit_logs_hash_chain` trigger uses, comparing against the stored
`row_hash`/`prev_hash`.

Recomputed **in one SQL query**, not re-implemented in Python — a Python
reimplementation of `concat_ws`/`::text` casting risks a false mismatch from
a formatting difference (JSONB canonicalization, timestamp precision) that
has nothing to do with real tampering. A single `LAG(...) OVER (ORDER BY
id)` window function lets Postgres do this in one pass, streamed back
rather than loaded into memory at once.

Runs over the `migrator` (BYPASSRLS) connection (`app/db/migrator.py`) —
this is the one thing in this codebase that must see every tenant's rows in
one query, never through the app's own RLS-scoped session.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.migrator import get_migrator_session

_VERIFY_SQL = text(
    """
    SELECT
        id,
        row_hash = encode(
            digest(
                concat_ws('|',
                    COALESCE(LAG(row_hash) OVER (ORDER BY id), ''),
                    company_id::text,
                    COALESCE(actor_user_id::text, ''),
                    action,
                    entity_type,
                    COALESCE(entity_id::text, ''),
                    COALESCE(old_data::text, ''),
                    COALESCE(new_data::text, ''),
                    source,
                    created_at::text
                ),
                'sha256'
            ),
            'hex'
        ) AS hash_matches,
        prev_hash IS NOT DISTINCT FROM LAG(row_hash) OVER (ORDER BY id) AS link_matches
    FROM audit_logs
    ORDER BY id
    """
)


@dataclass(frozen=True)
class ChainVerifyResult:
    rows_checked: int
    is_valid: bool
    #: The `audit_logs.id` of the first row whose hash or chain link didn't
    #: match — `None` when `is_valid` is True.
    first_broken_id: int | None


async def verify_chain(session: AsyncSession) -> ChainVerifyResult:
    result = await session.stream(_VERIFY_SQL)
    rows_checked = 0
    first_broken_id: int | None = None
    async for row in result:
        rows_checked += 1
        if first_broken_id is None and not (row.hash_matches and row.link_matches):
            first_broken_id = row.id
    return ChainVerifyResult(
        rows_checked=rows_checked,
        is_valid=first_broken_id is None,
        first_broken_id=first_broken_id,
    )


async def run() -> ChainVerifyResult:
    """The nightly entrypoint — opens its own `migrator` session, matching
    the other three task modules' `run()` convention. `verify_chain` stays
    the directly-testable core (tests pass their own superuser session,
    which already bypasses RLS the same way `migrator` does, without
    needing `DATABASE_URL_MIGRATOR` configured in the test environment)."""
    async with get_migrator_session() as session:
        return await verify_chain(session)
