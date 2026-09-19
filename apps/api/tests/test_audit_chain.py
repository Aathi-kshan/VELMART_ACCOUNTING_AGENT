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

import pytest
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


class TestEveryAuditedFieldIsTamperEvident:
    """The chain only means something if it covers what an attacker would
    change.

    Before migration 0018 it hashed ten fields and left six out, including
    `page_id` — which decides which page an entry belongs to and which
    managers can see it — plus `actor_role`, `diff`, `ai_session_id`,
    `ip_address` and `user_agent`. Any of those could be rewritten and the
    chain still verified clean, so the audit log was tamper-evident about
    *what* happened but not about *who* did it or *where* it was filed.

    These tests edit a committed row directly (the test role bypasses the
    REVOKE that stops `app_user` doing this) and require the verifier to
    notice.
    """

    @pytest.mark.parametrize(
        ("column", "value"),
        [
            ("page_id", "'00000000-0000-0000-0000-0000000000ff'::uuid"),
            ("actor_role", "'MANAGER'::user_role"),
            ("diff", "'{\"tampered\": true}'::jsonb"),
            ("ai_session_id", "'00000000-0000-0000-0000-0000000000aa'::uuid"),
            ("ip_address", "'203.0.113.1'::inet"),
            ("user_agent", "'forged'"),
        ],
    )
    async def test_altering_it_breaks_the_chain(
        self,
        client: AsyncClient,
        owner: uuid.UUID,
        owner_password: str,
        session: AsyncSession,
        column: str,
        value: str,
    ) -> None:
        from app.tasks.audit_chain_verify import verify_chain

        await _login(client, "owner@test.lk", owner_password, device_id="d1")

        target = (
            await session.execute(text("SELECT id FROM audit_logs ORDER BY id LIMIT 1"))
        ).scalar_one()

        before = await verify_chain(session)
        assert before.is_valid, "the chain was already broken before tampering"

        await session.execute(
            text(f"UPDATE audit_logs SET {column} = {value} WHERE id = :id"),  # noqa: S608
            {"id": target},
        )
        await session.commit()

        after = await verify_chain(session)
        assert not after.is_valid, f"altering {column} went undetected"
        assert after.first_broken_id == target


class TestConcurrentAuditWritesDoNotForkTheChain:
    async def test_parallel_requests_leave_a_verifiable_chain(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str, session: AsyncSession
    ) -> None:
        """0005 claimed `SELECT ... FOR UPDATE` on the tail row prevented two
        inserts sharing a `prev_hash`. Under READ COMMITTED it does not: both
        transactions can re-read the same locked row and fork the chain, which
        the verifier then reports as tampering. Migration 0018 serialises the
        insert with an advisory lock instead."""
        import asyncio

        from app.tasks.audit_chain_verify import verify_chain

        login = await client.post(
            "/auth/login",
            json={"email": "owner@test.lk", "password": owner_password, "device_id": "d1"},
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        page = await client.post(
            "/pages",
            json={"name": "Chain Race", "columns": [{"name": "Note", "data_type": "TEXT"}]},
            headers=headers,
        )
        assert page.status_code == 201, page.text
        page_id = page.json()["id"]

        # Every create writes an audit row, so these contend on the chain.
        responses = await asyncio.gather(
            *(
                client.post(
                    f"/pages/{page_id}/records",
                    json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"note": f"r{i}"}},
                    headers=headers,
                )
                for i in range(8)
            )
        )
        # Report the body, not just the code. These eight requests contend on
        # the chain's advisory lock, on one `rate_limits` row, and on a pool of
        # 10 connections, so when one does fail the reason matters and a bare
        # list of status codes says nothing about it.
        failures = [(r.status_code, r.text[:200]) for r in responses if r.status_code != 201]
        assert not failures, f"{len(failures)} of 8 concurrent creates failed: {failures}"

        result = await verify_chain(session)
        assert result.is_valid, (
            f"concurrent writes forked the chain at id {result.first_broken_id}"
        )


class TestTailTruncationIsDetected:
    """Deleting the newest rows leaves a chain that still links up perfectly.

    The hash chain proves no row *between* two others was altered, because
    each row's hash feeds the next — but it says nothing about the end. Cut
    the tail off and what remains verifies clean, which made the most likely
    way to cover a trail the one thing the chain could not see.

    `audit_chain_anchor` (migration 0019) records where the chain reached at
    the last clean verification, outside `audit_logs` and out of reach of the
    application's own database role.
    """

    async def test_removing_the_newest_rows_is_caught(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str, session: AsyncSession
    ) -> None:
        from app.tasks.audit_chain_verify import verify_chain

        for device in ("d1", "d2", "d3"):
            await _login(client, "owner@test.lk", owner_password, device_id=device)

        anchored = await verify_chain(session, update_anchor=True)
        assert anchored.is_valid
        assert anchored.rows_checked >= 3

        # Cut off the newest entry. The survivors still chain correctly.
        await session.execute(
            text("DELETE FROM audit_logs WHERE id = (SELECT max(id) FROM audit_logs)")
        )
        await session.commit()

        after = await verify_chain(session)
        assert after.truncation_detected, "the audit log lost rows and nothing noticed"
        assert not after.is_valid
        # The surviving rows are individually intact — which is exactly why
        # the row-by-row check alone could not catch this.
        assert after.first_broken_id is None

    async def test_a_clean_log_still_verifies(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str, session: AsyncSession
    ) -> None:
        """The anchor must not produce false alarms as the log grows."""
        from app.tasks.audit_chain_verify import verify_chain

        await _login(client, "owner@test.lk", owner_password, device_id="d1")
        first = await verify_chain(session, update_anchor=True)
        assert first.is_valid

        await _login(client, "owner@test.lk", owner_password, device_id="d2")
        second = await verify_chain(session, update_anchor=True)
        assert second.is_valid, "growth was mistaken for tampering"
        assert not second.truncation_detected
        assert second.rows_checked > first.rows_checked

    async def test_the_application_role_cannot_move_the_anchor(
        self, app_user_session: AsyncSession
    ) -> None:
        """An attacker holding the app's own database role must not be able
        to re-anchor to match a truncation they just made."""
        import pytest as _pytest
        from sqlalchemy.exc import ProgrammingError

        with _pytest.raises(ProgrammingError):
            async with app_user_session.begin():
                await app_user_session.execute(text("SELECT * FROM audit_chain_anchor"))
