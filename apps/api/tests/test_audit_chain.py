"""The audit hash chain (plan section 18.1, P5) — tamper-evident by
construction, not by policy. `row_hash`/`prev_hash` are computed only by the
`fn_audit_logs_hash_chain` trigger (migration 0005), never application code.

The chain is deliberately global across every company, not per-tenant — the
trigger's own lookup (`ORDER BY id DESC LIMIT 1`) has no `WHERE company_id`.
`app/tasks/audit_chain_verify.py` (P5, a later slice) walks this exact same
formula via SQL to detect tampering; the recomputation here is written the
same way (a SQL `LAG` window function, not a Python re-implementation of
`concat_ws`/`digest`) so there is no risk of a Python-vs-Postgres text
serialization mismatch (JSONB/timestamp formatting) producing a false
mismatch that has nothing to do with real tampering.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _login(client: AsyncClient, email: str, password: str, device_id: str = "d1") -> None:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": device_id}
    )
    assert resp.status_code == 200, resp.text


_RECOMPUTE_SQL = text(
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
        ) AS matches
    FROM audit_logs
    ORDER BY id
    """
)


class TestHashChainLinking:
    async def test_consecutive_inserts_link_via_prev_hash(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str, session: AsyncSession
    ) -> None:
        await _login(client, "owner@test.lk", owner_password, device_id="d1")
        await _login(client, "owner@test.lk", owner_password, device_id="d2")

        rows = (
            await session.execute(
                text("SELECT id, prev_hash, row_hash FROM audit_logs ORDER BY id")
            )
        ).all()
        assert len(rows) >= 2
        for earlier, later in zip(rows, rows[1:], strict=False):
            assert later.prev_hash == earlier.row_hash

    async def test_row_hash_matches_recomputation_of_the_exact_trigger_formula(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str, session: AsyncSession
    ) -> None:
        await _login(client, "owner@test.lk", owner_password, device_id="d1")
        # Deliberately wrong password — a LOGIN_FAILED entry with different
        # field values than the successful login above, so the recomputation
        # below isn't just proving one lucky case.
        await client.post(
            "/auth/login",
            json={"email": "owner@test.lk", "password": "wrong-password", "device_id": "d2"},
        )

        rows = (await session.execute(_RECOMPUTE_SQL)).all()
        assert rows
        assert all(row.matches for row in rows)


class TestHashChainIsGlobal:
    async def test_chain_interleaves_two_companies_in_one_global_order(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        company: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        from app.core.security import hash_password

        company_b = uuid.uuid4()
        await session.execute(
            text("INSERT INTO companies (id, name) VALUES (:id, 'Chain Test Co B')"),
            {"id": str(company_b)},
        )
        owner_b = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO users (id, company_id, email, full_name, password_hash, role) "
                "VALUES (:id, :company_id, 'chain-owner-b@test.lk', 'Owner B', :pw, 'OWNER')"
            ),
            {
                "id": str(owner_b),
                "company_id": str(company_b),
                "pw": hash_password("correct-horse-battery"),
            },
        )
        await session.commit()

        await _login(client, "owner@test.lk", owner_password, device_id="a1")
        await _login(client, "chain-owner-b@test.lk", "correct-horse-battery", device_id="b1")
        await _login(client, "owner@test.lk", owner_password, device_id="a2")

        rows = (
            await session.execute(
                text(
                    "SELECT company_id, prev_hash, row_hash FROM audit_logs "
                    "ORDER BY id DESC LIMIT 3"
                )
            )
        ).all()
        companies_seen = {row.company_id for row in rows}
        assert company in companies_seen
        assert company_b in companies_seen
        # The chain links across the company boundary — the middle (company
        # B) row's prev_hash is the earlier company-A row's row_hash, proving
        # there is no `WHERE company_id` anywhere in the trigger's own lookup.
        oldest, middle, newest = reversed(rows)
        assert middle.prev_hash == oldest.row_hash
        assert newest.prev_hash == middle.row_hash
