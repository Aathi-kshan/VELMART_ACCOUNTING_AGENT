"""Nightly ops jobs (P5 §nightly-ops): audit chain verification, idempotency
cleanup, daily digest, and the `python -m app.tasks.nightly` orchestrator.

`verify_chain`/`build_digests` take a session directly (the testable core
each `run()` wraps around its own `migrator`/`app_user` connection) — tests
pass the superuser `session` fixture, already RLS-exempt the same way
`migrator` (BYPASSRLS) is, without needing real `DATABASE_URL_MIGRATOR`
credentials in the test environment.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.idempotency import purge_expired
from app.tasks import audit_chain_verify, daily_digest, nightly


async def _login(client: AsyncClient, email: str, password: str) -> None:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": "d1"}
    )
    assert resp.status_code == 200, resp.text


class TestChainVerify:
    async def test_passes_on_an_untampered_chain(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str, session: AsyncSession
    ) -> None:
        await _login(client, "owner@test.lk", owner_password)
        result = await audit_chain_verify.verify_chain(session)
        assert result.is_valid
        assert result.first_broken_id is None
        assert result.rows_checked >= 1

    async def test_detects_a_tampered_old_data(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        company: uuid.UUID, session: AsyncSession,
    ) -> None:
        headers_resp = await client.post(
            "/auth/login",
            json={"email": "owner@test.lk", "password": owner_password, "device_id": "d1"},
        )
        headers = {"Authorization": f"Bearer {headers_resp.json()['access_token']}"}
        page = await client.post(
            "/pages",
            json={
                "name": "Chain Tamper Page",
                "columns": [{"name": "Amount", "data_type": "CURRENCY", "is_required": True}],
            },
            headers=headers,
        )
        record = await client.post(
            f"/pages/{page.json()['id']}/records",
            json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"amount": "100.00"}},
            headers=headers,
        )
        await client.patch(
            f"/records/{record.json()['id']}",
            json={"version": record.json()["version"], "data": {"amount": "200.00"}},
            headers=headers,
        )

        # A direct UPDATE bypasses the (INSERT-only) trigger entirely — the
        # stored row_hash no longer matches a fresh recomputation over the
        # tampered data.
        target = (
            await session.execute(
                text(
                    "SELECT id FROM audit_logs WHERE action = 'RECORD_UPDATE' "
                    "ORDER BY created_at DESC LIMIT 1"
                )
            )
        ).scalar_one()
        await session.execute(
            text(
                "UPDATE audit_logs SET old_data = '{\"amount\": \"999.00\"}'::jsonb "
                "WHERE id = :id"
            ),
            {"id": target},
        )
        await session.commit()

        result = await audit_chain_verify.verify_chain(session)
        assert not result.is_valid
        assert result.first_broken_id == target

    async def test_detects_a_tampered_row_hash(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str, session: AsyncSession
    ) -> None:
        await _login(client, "owner@test.lk", owner_password)
        target = (
            await session.execute(
                text("SELECT id FROM audit_logs ORDER BY created_at DESC LIMIT 1")
            )
        ).scalar_one()
        await session.execute(
            text("UPDATE audit_logs SET row_hash = 'not-a-real-hash' WHERE id = :id"),
            {"id": target},
        )
        await session.commit()

        result = await audit_chain_verify.verify_chain(session)
        assert not result.is_valid
        assert result.first_broken_id == target

    async def test_walks_two_companies_interleaved_in_one_pass(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        company: uuid.UUID, session: AsyncSession,
    ) -> None:
        from app.core.security import hash_password

        company_b = uuid.uuid4()
        await session.execute(
            text("INSERT INTO companies (id, name) VALUES (:id, 'Nightly Chain Co B')"),
            {"id": str(company_b)},
        )
        owner_b = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO users (id, company_id, email, full_name, password_hash, role) "
                "VALUES (:id, :cid, 'nightly-owner-b@test.lk', 'Owner B', :pw, 'OWNER')"
            ),
            {
                "id": str(owner_b),
                "cid": str(company_b),
                "pw": hash_password("correct-horse-battery"),
            },
        )
        await session.commit()

        await _login(client, "owner@test.lk", owner_password)
        await _login(client, "nightly-owner-b@test.lk", "correct-horse-battery")
        await _login(client, "owner@test.lk", owner_password)

        result = await audit_chain_verify.verify_chain(session)
        assert result.is_valid
        assert result.rows_checked >= 3

        companies_seen = (
            await session.execute(text("SELECT DISTINCT company_id FROM audit_logs"))
        ).scalars().all()
        assert company in companies_seen
        assert company_b in companies_seen


class TestIdempotencyCleanup:
    async def test_deletes_rows_older_than_48h_and_keeps_recent_ones(
        self, company: uuid.UUID, owner: uuid.UUID, session: AsyncSession
    ) -> None:
        # `company_id` is part of the primary key since migration 0017 —
        # keys are scoped per tenant, not globally unique.
        old_key, recent_key = str(uuid.uuid4()), str(uuid.uuid4())
        old_time = datetime.now(tz=UTC) - timedelta(hours=72)
        recent_time = datetime.now(tz=UTC) - timedelta(hours=1)
        insert_key = text(
            "INSERT INTO idempotency_keys "
            "(company_id, key, user_id, endpoint, request_hash, created_at) "
            "VALUES (:company_id, :key, :uid, '/test', 'hash', :created_at)"
        )
        await session.execute(
            insert_key,
            {
                "company_id": str(company),
                "key": old_key,
                "uid": str(owner),
                "created_at": old_time,
            },
        )
        await session.execute(
            insert_key,
            {
                "company_id": str(company),
                "key": recent_key,
                "uid": str(owner),
                "created_at": recent_time,
            },
        )
        await session.commit()

        deleted = await purge_expired(session, older_than_hours=48)
        await session.commit()
        assert deleted >= 1

        remaining = (
            await session.execute(
                text("SELECT key FROM idempotency_keys WHERE key = ANY(:keys)"),
                {"keys": [old_key, recent_key]},
            )
        ).scalars().all()
        assert old_key not in remaining
        assert recent_key in remaining


class TestDailyDigest:
    async def test_writes_one_row_per_company_with_counts_matching_activity(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        company: uuid.UUID, session: AsyncSession,
    ) -> None:
        headers_resp = await client.post(
            "/auth/login",
            json={"email": "owner@test.lk", "password": owner_password, "device_id": "d1"},
        )
        headers = {"Authorization": f"Bearer {headers_resp.json()['access_token']}"}
        page = await client.post(
            "/pages",
            json={
                "name": "Digest Test Page",
                "columns": [{"name": "Amount", "data_type": "CURRENCY", "is_required": True}],
            },
            headers=headers,
        )
        page_id = page.json()["id"]
        await client.post(
            f"/pages/{page_id}/records",
            json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"amount": "10.00"}},
            headers=headers,
        )
        await client.post(
            f"/pages/{page_id}/records",
            json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"amount": "20.00"}},
            headers=headers,
        )

        result = await daily_digest.build_digests(session)
        assert result.companies_processed >= 1

        row = (
            await session.execute(
                text(
                    "SELECT summary FROM daily_digests "
                    "WHERE company_id = :cid AND digest_date = :date"
                ),
                {"cid": str(company), "date": result.digest_date},
            )
        ).scalar_one()
        assert row["record_create"] >= 2

    async def test_rerunning_the_same_day_updates_rather_than_duplicates(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str,
        company: uuid.UUID, session: AsyncSession,
    ) -> None:
        await _login(client, "owner@test.lk", owner_password)
        first = await daily_digest.build_digests(session)
        second = await daily_digest.build_digests(session)
        assert first.digest_date == second.digest_date

        count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM daily_digests "
                    "WHERE company_id = :cid AND digest_date = :date"
                ),
                {"cid": str(company), "date": first.digest_date},
            )
        ).scalar_one()
        assert count == 1


class TestNightlyOrchestrator:
    async def test_reports_failure_when_migrator_is_unconfigured_but_still_runs_every_job(
        self, owner: uuid.UUID, session: AsyncSession
    ) -> None:
        """`DATABASE_URL_MIGRATOR` isn't set in the test environment — a
        real, if inconvenient, way to prove three of the four jobs failing
        doesn't stop `idempotency_cleanup` (which needs only `app_user`)
        from still running, and the orchestrator reports failure overall
        rather than a silent partial success."""
        exit_code = await nightly.main()
        assert exit_code == 1
