"""Seed a realistic-volume company so the restore drill measures a real RTO.

`infra/scripts/restore_drill.sh` proved the *procedure* works — restore,
verify migration head, verify every table's row count, verify the audit
chain — but its first recorded run was against 458 development rows. That
number is not a Recovery Time Objective. It answers "does the script work?",
not "how long would restoring this database actually take?" — and those can
differ by orders of magnitude once a real backup is gigabytes, not
kilobytes.

This seeds a dedicated company at the same scale this project already treats
as production-representative: 100,000 rows (`VELMART_RTO_ROWS`), the same
default `tests/perf/test_volume.py` uses and the same figure
`docs/PROJECT_PLAN.md`'s own volume target cites. Split across both storage
paths the engine has to restore correctly — a generic `kind=LEDGER` page
(JSONB `records`, the harder path: GIN/expression indexes, a projection
slot, a FORMULA column) and a native system table (`expenses`, real typed
columns) — so the drill exercises the same two code paths
`test_storage_parity` exists to prove agree.

Rows are bulk-inserted directly, the same choice `test_volume.py` makes and
for the same reason: the point is restore-time volume, not proving 100,000
individual `POST /records` calls work (that is what the rest of the test
suite is for).

Usage, from `apps/api` with `DATABASE_URL` pointed at the database to load:

    uv run python ../../infra/scripts/seed_rto_drill_data.py --seed
    uv run python ../../infra/scripts/seed_rto_drill_data.py --cleanup <company_id>

**Cleanup does not touch `audit_logs`.** The hash chain (migration 0005) is
one global sequence across every company by design — there is no
`WHERE company_id` in the trigger — so deleting this company's audit rows
after the fact would delete from the *middle* of that chain, breaking
`link_matches` for every row after the gap for every tenant, not just this
one. `companies` cascades everything else (`ON DELETE CASCADE` on every
`company_id` foreign key), so `--cleanup` removes the company, its users,
pages and every row seeded here — the handful of `PAGE_CREATE`/system-page
audit entries this run produces are left in place permanently, harmless and
correctly attributed to a company that no longer exists.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.security import hash_password
from app.db.base import RecordStatus
from app.db.rls import set_rls_context
from app.db.session import get_sessionmaker
from app.models.business import Expense
from app.models.record import Record
from app.models.user import UserRole
from app.schemas.column import ColumnDefinition
from app.schemas.page import CreatePageRequest
from app.services.page_service import create_page, get_page_by_key, register_system_pages

DRILL_COMPANY_NAME = "RTO Drill Volume Test"
DRILL_OWNER_EMAIL = "rto-drill@velmart-internal.test"
DRILL_OWNER_PASSWORD = "not-a-real-account-drill-only"  # noqa: S105 - synthetic, local-only

ROW_COUNT = int(os.environ.get("VELMART_RTO_ROWS", "100000"))
_BATCH_SIZE = 5_000


async def _create_drill_company_and_owner(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """Always a fresh company — this script measures a one-shot drill, not a
    reusable fixture, and re-running with stale seeded data would understate
    the very thing it exists to measure."""
    existing = await session.scalar(
        text("SELECT id FROM companies WHERE name = :name"), {"name": DRILL_COMPANY_NAME}
    )
    if existing is not None:
        raise SystemExit(
            f"A company named {DRILL_COMPANY_NAME!r} already exists ({existing}). "
            f"Run --cleanup {existing} first, or this run would seed on top of it."
        )

    company_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO companies (id, name) VALUES (:id, :name)"),
        {"id": str(company_id), "name": DRILL_COMPANY_NAME},
    )

    await set_rls_context(session, company_id=company_id, role=UserRole.OWNER.value)
    owner_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO users (id, company_id, email, full_name, password_hash, role)
            VALUES (:id, :company_id, :email, 'RTO Drill Owner', :pw, 'OWNER')
            """
        ),
        {
            "id": str(owner_id),
            "company_id": str(company_id),
            "email": DRILL_OWNER_EMAIL,
            "pw": hash_password(DRILL_OWNER_PASSWORD),
        },
    )
    return company_id, owner_id


async def _seed_ledger_page(
    session: AsyncSession, company_id: uuid.UUID, owner_id: uuid.UUID
) -> int:
    """The generic-page/JSONB path: an indexed CURRENCY column (exercises the
    projection slot), a SELECT, and a FORMULA — the mix
    `tests/perf/test_volume.py` uses, seeded here the same way."""
    ctx = SecurityContext(
        user_id=owner_id, company_id=company_id, role=UserRole.OWNER, store_ids=()
    )
    page = await create_page(
        session,
        ctx,
        CreatePageRequest(
            name="RTO Drill Ledger",
            kind="LEDGER",  # type: ignore[arg-type]
            columns=[
                ColumnDefinition(
                    name="Amount",
                    data_type="CURRENCY",  # type: ignore[arg-type]
                    is_required=True,
                    is_indexed=True,
                    config={"allow_negative": True},
                ),
                ColumnDefinition(
                    name="Category",
                    data_type="SELECT",  # type: ignore[arg-type]
                    config={"options": ["Sales", "Refund", "Adjustment"]},
                ),
                ColumnDefinition(
                    name="Total", data_type="FORMULA", config={"expression": "amount"}  # type: ignore[arg-type]
                ),
            ],
            balance_column_key="amount",
        ),
    )
    await session.flush()

    reloaded = await get_page_by_key(session, company_id, "rto_drill_ledger")
    assert reloaded is not None
    num_slot = reloaded.projection_map["amount"]

    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    categories = ["Sales", "Refund", "Adjustment"]
    rows: list[dict[str, object]] = []
    inserted = 0
    for i in range(ROW_COUNT):
        amount = Decimal(100 + (i % 5000)).quantize(Decimal("0.01"))
        occurred_at = base_time + timedelta(minutes=i)
        rows.append(
            {
                "id": uuid.uuid4(),
                "company_id": company_id,
                "page_id": page.id,
                "occurred_at": occurred_at,
                "business_date": occurred_at.date(),
                "data": {"amount": str(amount), "category": categories[i % 3]},
                "status": RecordStatus.ACTIVE,
                "created_by": owner_id,
                num_slot: amount,
            }
        )
        if len(rows) >= _BATCH_SIZE:
            await session.execute(insert(Record), rows)
            inserted += len(rows)
            rows = []
    if rows:
        await session.execute(insert(Record), rows)
        inserted += len(rows)
    return inserted


async def _seed_expenses(session: AsyncSession, company_id: uuid.UUID, owner_id: uuid.UUID) -> int:
    """The native/system-table path — real typed columns, not JSONB."""
    ctx = SecurityContext(
        user_id=owner_id, company_id=company_id, role=UserRole.OWNER, store_ids=()
    )
    await register_system_pages(session, ctx, company_id)

    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    names = ["Electricity", "Rent", "Water", "Transport", "Repairs"]
    rows: list[dict[str, object]] = []
    inserted = 0
    for i in range(ROW_COUNT):
        occurred_at = base_time + timedelta(minutes=i)
        rows.append(
            {
                "id": uuid.uuid4(),
                "company_id": company_id,
                "occurred_at": occurred_at,
                "business_date": occurred_at.date(),
                "status": RecordStatus.ACTIVE,
                "created_by": owner_id,
                "expense_date": occurred_at.date(),
                "expense_name": names[i % len(names)],
                "amount": Decimal(50 + (i % 3000)).quantize(Decimal("0.01")),
            }
        )
        if len(rows) >= _BATCH_SIZE:
            await session.execute(insert(Expense), rows)
            inserted += len(rows)
            rows = []
    if rows:
        await session.execute(insert(Expense), rows)
        inserted += len(rows)
    return inserted


async def seed() -> uuid.UUID:
    session_factory = get_sessionmaker()
    start = time.perf_counter()
    async with session_factory() as session, session.begin():
        company_id, owner_id = await _create_drill_company_and_owner(session)
        ledger_rows = await _seed_ledger_page(session, company_id, owner_id)
        expense_rows = await _seed_expenses(session, company_id, owner_id)
    elapsed = time.perf_counter() - start

    print(f"Seeded company {DRILL_COMPANY_NAME} ({company_id})")
    print(f"  {ledger_rows:,} rows in records (generic LEDGER page)")
    print(f"  {expense_rows:,} rows in expenses (native system page)")
    print(f"  {ledger_rows + expense_rows:,} rows total, in {elapsed:.1f}s")
    print()
    print(f"Cleanup: uv run python {Path(__file__).name} --cleanup {company_id}")
    return company_id


async def cleanup(company_id: uuid.UUID) -> None:
    """Removes the drill company and everything `ON DELETE CASCADE` reaches
    from it. Deliberately does not touch `audit_logs` — see the module
    docstring.

    Deletes `records` and `expenses` explicitly, in their own transactions,
    before touching `companies` at all. Two things forced that shape, both
    found by running this function for real rather than trusting it:

    `records` carries a GIN index on its JSONB `data` column plus a
    trigram-search index (`app/models/record.py`'s own comment names both) —
    deleting 100,000 rows through them took **2m19s** measured directly, an
    order of magnitude past `DB_STATEMENT_TIMEOUT_MS`'s 15s default and past
    a first attempt at raising it to 120s. GIN/trigram index maintenance on
    delete is expensive by nature, not a bug in this script; `expenses` has
    no such indexes and the same 100,000 rows took 67ms.

    Cascading through `companies` in one statement also could not be timed
    or reasoned about in isolation — the slow part was entirely attributable
    to `records` once split out.
    """
    session_factory = get_sessionmaker()

    async with session_factory() as session, session.begin():
        name = await session.scalar(
            text("SELECT name FROM companies WHERE id = :id"), {"id": str(company_id)}
        )
        if name is None:
            raise SystemExit(f"No company {company_id} — nothing to clean up.")

    # Each big table gets its own transaction and a generous timeout —
    # `DB_STATEMENT_TIMEOUT_MS` (app/config.py) is 15s by default, correct
    # for an ordinary request and far too short for this deliberately bulky
    # admin operation.
    for table in ("records", "expenses"):
        async with session_factory() as session, session.begin():
            await session.execute(text("SET LOCAL statement_timeout = '10min'"))
            await session.execute(
                text(f"DELETE FROM {table} WHERE company_id = :id"),  # noqa: S608 - fixed name
                {"id": str(company_id)},
            )

    async with session_factory() as session, session.begin():
        # Whatever is left (pages, users, stores, ...) is small — the
        # company row's own cascade handles it in milliseconds.
        await session.execute(
            text("DELETE FROM companies WHERE id = :id"), {"id": str(company_id)}
        )
    print(f"Removed {name!r} ({company_id}) and everything cascaded from it.")
    print("audit_logs rows for it were left in place — see the module docstring for why.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seed", action="store_true", help=f"Seed {ROW_COUNT:,} rows per table")
    group.add_argument("--cleanup", metavar="COMPANY_ID", help="Remove a previously seeded company")
    args = parser.parse_args()

    if args.seed:
        asyncio.run(seed())
    else:
        asyncio.run(cleanup(uuid.UUID(args.cleanup)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
