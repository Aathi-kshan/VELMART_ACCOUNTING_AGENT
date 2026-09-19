"""Nightly audit hash-chain verification (plan section 18.1, P5).

Walks `audit_logs` in true global chain order (the chain is one sequence
across every company — the trigger itself has no `WHERE company_id`, see
migration 0005) and recomputes each row's expected hash with the *exact
same* `concat_ws('|', ...)` + `digest(..., 'sha256')` formula the
`fn_audit_logs_hash_chain` trigger uses, comparing against the stored
`row_hash`/`prev_hash`.

Recomputed **in one SQL query**, not re-implemented in Python — a Python
reimplementation of `concat_ws`/`::text` casting risks a false mismatch from
a formatting difference (JSONB canonicalization, timestamp precision) that
has nothing to do with real tampering. A single `LAG(...) OVER (ORDER BY
chain_seq)` window function lets Postgres do this in one pass, streamed
back rather than loaded into memory at once.

Runs over the `migrator` (BYPASSRLS) connection (`app/db/migrator.py`) —
this is the one thing in this codebase that must see every tenant's rows in
one query, never through the app's own RLS-scoped session.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.migrator import get_migrator_session

#: Must stay identical to the field list in `fn_audit_logs_hash_chain`
#: (migrations 0018/0021). Ordered by `chain_seq`, not `id`: the id is a
#: BIGSERIAL assigned before the trigger takes the chain lock, so under
#: concurrency rows can be linked in one order and numbered in another —
#: walking by id then reports a well-formed chain as tampered with.
#: `chain_seq` is allocated inside the lock, so it is the linking order.
#:
#: The field list covers every audited field, not just the ten 0005
#: originally hashed — `page_id` decides which page an entry belongs to and
#: who can see it, `actor_role` records who acted, and `ai_session_id`
#: records whether the AI did, so all of them have to be tamper-evident.
_VERIFY_SQL = text(
    """
    SELECT
        id,
        row_hash = encode(
            digest(
                concat_ws('|',
                    COALESCE(LAG(row_hash) OVER (ORDER BY chain_seq), ''),
                    company_id::text,
                    COALESCE(actor_user_id::text, ''),
                    COALESCE(actor_role::text, ''),
                    action,
                    entity_type,
                    COALESCE(entity_id::text, ''),
                    COALESCE(page_id::text, ''),
                    COALESCE(old_data::text, ''),
                    COALESCE(new_data::text, ''),
                    COALESCE(diff::text, ''),
                    source,
                    COALESCE(ai_session_id::text, ''),
                    COALESCE(ip_address::text, ''),
                    COALESCE(user_agent, ''),
                    created_at::text
                ),
                'sha256'
            ),
            'hex'
        ) AS hash_matches,
        prev_hash IS NOT DISTINCT FROM LAG(row_hash) OVER (ORDER BY chain_seq)
            AS link_matches
    FROM audit_logs
    ORDER BY chain_seq
    """
)


@dataclass(frozen=True)
class ChainVerifyResult:
    rows_checked: int
    is_valid: bool
    #: The `audit_logs.id` of the first row whose hash or chain link didn't
    #: match — `None` when `is_valid` is True.
    first_broken_id: int | None
    #: Set when the chain itself links up but the log has lost rows off the
    #: end since the last successful verification — see `_check_anchor`.
    truncation_detected: bool = False


async def _check_anchor(session: AsyncSession, rows_checked: int) -> bool:
    """Compare the log against the last verified chain head.

    The chain proves nothing about its own end: delete the newest `k` rows
    and what remains still links up perfectly. Since deleting recent entries
    is the obvious way to cover a trail, that gap mattered.

    `audit_chain_anchor` (migration 0019) records where the chain reached the
    last time it verified. Truncation shows up as the anchored row having
    vanished, its hash having changed, or the table simply holding fewer rows
    than it did. Returns True when truncation is detected.
    """
    anchor = (
        await session.execute(
            text("SELECT last_id, last_row_hash, row_count FROM audit_chain_anchor")
        )
    ).mappings().one_or_none()
    if anchor is None:
        return False  # First run: nothing to compare against yet.

    if rows_checked < anchor["row_count"]:
        return True

    still_there = await session.scalar(
        text("SELECT row_hash FROM audit_logs WHERE chain_seq = :id"), {"id": anchor["last_id"]}
    )
    return still_there != anchor["last_row_hash"]


async def _record_anchor(session: AsyncSession, rows_checked: int) -> None:
    """Move the anchor forward after a clean verification."""
    head = (
        await session.execute(
            text("SELECT chain_seq, row_hash FROM audit_logs ORDER BY chain_seq DESC LIMIT 1")
        )
    ).mappings().one_or_none()
    if head is None:
        return

    await session.execute(
        text(
            """
            INSERT INTO audit_chain_anchor (only_row, last_id, last_row_hash, row_count)
            VALUES (true, :last_id, :last_row_hash, :row_count)
            ON CONFLICT (only_row) DO UPDATE SET
                last_id = EXCLUDED.last_id,
                last_row_hash = EXCLUDED.last_row_hash,
                row_count = EXCLUDED.row_count,
                verified_at = now()
            """
        ),
        {
            "last_id": head["chain_seq"],
            "last_row_hash": head["row_hash"],
            "row_count": rows_checked,
        },
    )


async def verify_chain(session: AsyncSession, *, update_anchor: bool = False) -> ChainVerifyResult:
    """Walk the whole chain. `update_anchor` is off by default so tests and
    ad-hoc checks are read-only; the nightly `run()` turns it on."""
    result = await session.stream(_VERIFY_SQL)
    rows_checked = 0
    first_broken_id: int | None = None
    async for row in result:
        rows_checked += 1
        if first_broken_id is None and not (row.hash_matches and row.link_matches):
            first_broken_id = row.id

    truncated = await _check_anchor(session, rows_checked)
    is_valid = first_broken_id is None and not truncated

    if update_anchor and is_valid:
        await _record_anchor(session, rows_checked)
        await session.commit()

    return ChainVerifyResult(
        rows_checked=rows_checked,
        is_valid=is_valid,
        first_broken_id=first_broken_id,
        truncation_detected=truncated,
    )


async def run() -> ChainVerifyResult:
    """The nightly entrypoint — opens its own `migrator` session, matching
    the other three task modules' `run()` convention. `verify_chain` stays
    the directly-testable core (tests pass their own superuser session,
    which already bypasses RLS the same way `migrator` does, without
    needing `DATABASE_URL_MIGRATOR` configured in the test environment)."""
    async with get_migrator_session() as session:
        return await verify_chain(session, update_anchor=True)
