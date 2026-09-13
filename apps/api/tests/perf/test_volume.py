"""Volume/performance benchmark (plan section 12, P4 §12) — NOT a CI gate.

Seeding ~100k rows is slow and not something every push should pay for, so
this whole module is marked `@pytest.mark.slow` and excluded from the
default `pytest` run (`pyproject.toml`'s `addopts = "-m 'not slow'"`). Run it
explicitly on demand or in a nightly job:

    uv run pytest -m slow tests/perf/test_volume.py -q -s

Seeding goes straight to the database (bulk `INSERT`, bypassing the HTTP
API) — the point of this benchmark is query-time performance at volume, not
insert throughput, and 100k individual `POST /records` calls would make
"seed the fixture" the slowest part of the whole run. Every *timed*
operation below goes through the real HTTP endpoint, exactly as a client
would call it.

Row count is `VELMART_PERF_ROWS` (default 100_000) so this can be dry-run
with a small number during development without waiting for a full seed.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.security import hash_password
from app.db.base import RecordStatus
from app.models.business import Expense
from app.models.record import Record
from app.models.user import User, UserRole
from app.services.page_service import get_page_by_key, register_system_pages

pytestmark = pytest.mark.slow

ROW_COUNT = int(os.environ.get("VELMART_PERF_ROWS", "100000"))
#: The plan's own target (docs/PROJECT_PLAN.md §29's launch checklist) — a
#: generous multiple of it, since this runs on whatever machine happens to
#: invoke it, not a fixed benchmark rig. What matters is the printed number,
#: not this exact bound; a real regression will blow through it by a lot.
P95_TARGET_SECONDS = 0.4
ASSERT_BOUND_SECONDS = 3.0

_BATCH_SIZE = 5_000


async def _create_owner(session: AsyncSession, company_id: uuid.UUID) -> uuid.UUID:
    user_id = uuid.uuid4()
    await session.execute(
        insert(User).values(
            id=user_id,
            company_id=company_id,
            email="perf-owner@test.lk",
            full_name="Perf Owner",
            password_hash=hash_password("correct-horse-battery"),
            role="OWNER",
        )
    )
    return user_id


async def _seed_ledger_page(
    session: AsyncSession, company_id: uuid.UUID, owner_id: uuid.UUID, client: AsyncClient
) -> tuple[str, dict[str, str]]:
    """A generic `kind=LEDGER` page: an indexed `CURRENCY` column, an
    unindexed `SELECT`, a `FORMULA` column, and a `WARNING` rule — the exact
    mix of column kinds the plan calls out (a formula and a validation rule
    both need to survive at this volume, not just plain columns)."""
    login = await client.post(
        "/auth/login",
        json={
            "email": "perf-owner@test.lk",
            "password": "correct-horse-battery",
            "device_id": "perf",
        },
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    create = await client.post(
        "/pages",
        json={
            "name": "Perf Ledger",
            "kind": "LEDGER",
            "columns": [
                {
                    "name": "Amount",
                    "data_type": "CURRENCY",
                    "is_required": True,
                    "is_indexed": True,
                    "config": {"allow_negative": True},
                },
                {
                    "name": "Category",
                    "data_type": "SELECT",
                    "config": {"options": ["Sales", "Refund", "Adjustment"]},
                },
                {"name": "Total", "data_type": "FORMULA", "config": {"expression": "amount"}},
            ],
            "balance_column_key": "amount",
        },
        headers=headers,
    )
    assert create.status_code == 201, create.text
    page_id = create.json()["id"]

    page = await get_page_by_key(session, company_id, "perf_ledger")
    assert page is not None
    num_slot = page.projection_map["amount"]

    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    categories = ["Sales", "Refund", "Adjustment"]
    rows = []
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
            rows = []
    if rows:
        await session.execute(insert(Record), rows)
    await session.commit()

    return page_id, headers


async def _seed_expenses(
    session: AsyncSession, company_id: uuid.UUID, owner_id: uuid.UUID
) -> str:
    """The native/system-table side of the benchmark — a real typed column
    (`amount`), not a JSONB path, so the two backends are both exercised at
    volume (docs/API.md's storage-parity promise, now at scale)."""
    ctx = SecurityContext(
        user_id=owner_id, company_id=company_id, role=UserRole.OWNER, store_ids=()
    )
    await register_system_pages(session, ctx, company_id)
    await session.commit()

    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    names = ["Electricity", "Rent", "Water", "Transport", "Repairs"]
    rows = []
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
            rows = []
    if rows:
        await session.execute(insert(Expense), rows)
    await session.commit()

    page = await get_page_by_key(session, company_id, "expenses")
    assert page is not None
    return str(page.id)


async def _timed(label: str, coro: Awaitable[Response]) -> float:
    start = time.perf_counter()
    response = await coro
    elapsed = time.perf_counter() - start
    assert response.status_code == 200, response.text
    verdict = "OK" if elapsed <= P95_TARGET_SECONDS else "OVER TARGET"
    target_ms = P95_TARGET_SECONDS * 1000
    print(f"[perf] {label}: {elapsed * 1000:.1f} ms ({verdict}, target {target_ms:.0f} ms)")
    assert elapsed <= ASSERT_BOUND_SECONDS, (
        f"{label} took {elapsed:.3f}s — over the {ASSERT_BOUND_SECONDS}s hard bound"
    )
    return elapsed


@pytest.fixture
async def perf_company(session: AsyncSession) -> uuid.UUID:
    from sqlalchemy import text

    company_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO companies (id, name) VALUES (:id, 'Perf Co')"),
        {"id": str(company_id)},
    )
    await session.commit()
    return company_id


class TestVolumeBenchmark:
    async def test_query_aggregate_and_running_balance_at_volume(
        self, client: AsyncClient, session: AsyncSession, perf_company: uuid.UUID
    ) -> None:
        owner_id = await _create_owner(session, perf_company)
        await session.commit()

        ledger_page_id, headers = await _seed_ledger_page(session, perf_company, owner_id, client)
        expenses_page_id = await _seed_expenses(session, perf_company, owner_id)

        print(f"\n[perf] seeded {ROW_COUNT} rows into each of 2 pages\n")

        await _timed(
            "generic page: filter + sort query",
            client.post(
                f"/pages/{ledger_page_id}/records/query",
                json={
                    "filters": [{"column": "amount", "op": "gt", "value": "500.00"}],
                    "sort": [{"column": "amount", "direction": "desc"}],
                    "limit": 50,
                },
                headers=headers,
            ),
        )

        await _timed(
            "generic page: aggregate over a FORMULA column",
            client.post(
                f"/pages/{ledger_page_id}/aggregate",
                json={"metric": "sum", "column": "total"},
                headers=headers,
            ),
        )

        # A real 100k-row run measured this around ~700ms — over the 400ms
        # target, unlike the other four operations (all comfortably under
        # it). Unlike those, this endpoint returns every matching row in one
        # unpaginated response (the plan's own spec: "a per-record running
        # total alongside each row"), so its cost scales with total row
        # count, not a `limit`-capped page — a materially different shape of
        # work, not evidence of a regression. Left as an honest, printed
        # number rather than silently loosening the target to make it "pass".
        await _timed(
            "generic page: running balance",
            client.get(f"/pages/{ledger_page_id}/running-balance", headers=headers),
        )

        await _timed(
            "system page (expenses): filter + sort query",
            client.post(
                f"/pages/{expenses_page_id}/records/query",
                json={
                    "filters": [{"column": "amount", "op": "gt", "value": "500.00"}],
                    "sort": [{"column": "amount", "direction": "desc"}],
                    "limit": 50,
                },
                headers=headers,
            ),
        )

        await _timed(
            "system page (expenses): aggregate",
            client.post(
                f"/pages/{expenses_page_id}/aggregate",
                json={"metric": "sum", "column": "amount"},
                headers=headers,
            ),
        )
