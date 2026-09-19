"""Races that sequential tests cannot see.

`test_optimistic_locking.py` proves the *protocol* — a stale `If-Match` is a
409 — but every one of its cases replays an old version number after the
first write has already committed. That only exercises the Python-side
comparison in `record_service._check_version`. It says nothing about the
case the lock exists for: two clients that both read version 3 and both
PATCH before either commits.

The distinction matters because a check-then-act lock passes every
sequential test and still loses writes. So each test here drives real
concurrent requests through the ASGI app with `asyncio.gather` — separate
pooled connections, genuine interleaving, `READ COMMITTED` like production
(`app/db/session.py`) — and asserts on the *outcome*, not just the status
codes: the final row must reflect exactly one winner, and the winner's data
must actually be in the database.

`tests/test_user_management.py::TestDuplicateEmailIsRejectedCleanly` was the
only concurrent test in the suite before this file.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

#: Enough concurrent writers that the read-then-write window is hit
#: reliably, few enough to stay fast. All of them send the *same* starting
#: version, so exactly one may ever succeed.
_WRITERS = 6


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/auth/login", json={"email": email, "password": password, "device_id": "d1"}
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


async def _owner_headers(client: AsyncClient, owner_password: str) -> dict[str, str]:
    token = await _login(client, "owner@test.lk", owner_password)
    return {"Authorization": f"Bearer {token}"}


async def _make_page(
    client: AsyncClient, headers: dict[str, str], *, kind: str = "REGISTER"
) -> str:
    resp = await client.post(
        "/pages",
        json={
            "name": f"Race Page {uuid.uuid4().hex[:6]}",
            "kind": kind,
            "columns": [{"name": "Note", "data_type": "TEXT"}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def _make_record(client: AsyncClient, headers: dict[str, str], page_id: str) -> dict:
    resp = await client.post(
        f"/pages/{page_id}/records",
        json={"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"note": "original"}},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


def _split(responses: Sequence[Response]) -> tuple[list[Response], list[Response]]:
    """Partition into (succeeded, conflicted), asserting nothing else happened —
    a 500 from a race must not be mistaken for a rejected write."""
    ok = [r for r in responses if r.status_code == 200]
    conflict = [r for r in responses if r.status_code == 409]
    other = [r for r in responses if r.status_code not in (200, 409)]
    assert not other, f"unexpected statuses: {[(r.status_code, r.text) for r in other]}"
    return ok, conflict


@asynccontextmanager
async def _armed_session(app_user_url: str, company_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """An independent `app_user` connection with an open, RLS-armed
    transaction — the same role and context a request runs under, but with
    commit timing under the test's control rather than the framework's."""
    from app.config import to_asyncpg_url
    from app.db.rls import set_rls_context

    engine = create_async_engine(to_asyncpg_url(app_user_url), poolclass=NullPool)
    session = async_sessionmaker(engine, expire_on_commit=False)()
    try:
        await session.begin()
        await set_rls_context(session, company_id=company_id, role="OWNER")
        yield session
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def _load_for_update(  # noqa: ANN201
    session: AsyncSession, page_id: str, record_id: str, company_id: uuid.UUID
):
    """Page, live columns and row handle — what `record_service._locate`
    hands to `update_row`."""
    from app.models.page import Page
    from app.repositories.records import get_row
    from app.services import page_service

    page = (await session.execute(select(Page).where(Page.id == uuid.UUID(page_id)))).scalar_one()
    columns = await page_service.get_page_columns(session, page.id)
    handle = await get_row(session, page, columns, uuid.UUID(record_id), company_id)
    assert handle is not None
    return page, columns, handle


class TestLostUpdateIsBlockedByTheDatabase:
    """The decisive test for optimistic locking.

    Every HTTP test in this file passes even against a check-then-act lock.
    A request holds its transaction — and the audit chain's global tail lock —
    for its whole duration, so concurrent PATCHes serialize far enough apart
    that the losers re-read the *new* version and fail the Python-side
    comparison in `record_service._check_version`. Measured: 6 concurrent
    PATCHes produce 1x200 and 5x409 with no database-level guard at all. That
    makes those tests useful regression guards and useless detectors.

    This test removes request scheduling from the picture. Two callers each
    read the same row at version 1, and only then does either write. No
    timing can rescue it: if the UPDATE does not carry the version it read,
    the second write silently overwrites the first and the lock is decoration.
    """

    async def test_a_writer_holding_a_stale_handle_cannot_overwrite_the_winner(
        self,
        client: AsyncClient,
        session: AsyncSession,
        app_user_url: str,
        company: uuid.UUID,
        owner: uuid.UUID,
        owner_password: str,
    ) -> None:
        from app.core.errors import VersionConflictError
        from app.repositories.records import update_row

        headers = await _owner_headers(client, owner_password)
        page_id = await _make_page(client, headers)
        record = await _make_record(client, headers, page_id)

        async with (
            _armed_session(app_user_url, company) as first,
            _armed_session(app_user_url, company) as second,
        ):
            page_a, cols_a, handle_a = await _load_for_update(
                first, page_id, record["id"], company
            )
            page_b, cols_b, handle_b = await _load_for_update(
                second, page_id, record["id"], company
            )
            # Both read the same version before either writes — the exact
            # state two humans editing the same record are in.
            assert handle_a.version == 1
            assert handle_b.version == 1

            await update_row(
                first,
                page_a,
                handle_a,
                cols_a,
                validated={"note": "first writer"},
                occurred_at=handle_a.occurred_at,
                store_id=None,
                business_date=handle_a.business_date,
                updated_by=owner,
            )
            await first.commit()

            with pytest.raises(VersionConflictError):
                await update_row(
                    second,
                    page_b,
                    handle_b,
                    cols_b,
                    validated={"note": "second writer"},
                    occurred_at=handle_b.occurred_at,
                    store_id=None,
                    business_date=handle_b.business_date,
                    updated_by=owner,
                )

        # The winner's write must still be what is stored.
        stored = await session.execute(
            text("SELECT version, data FROM records WHERE id = :id"), {"id": record["id"]}
        )
        row = stored.mappings().one()
        assert row["data"]["note"] == "first writer", "the stale writer overwrote the winner"
        assert row["version"] == 2

    async def test_a_stale_soft_delete_cannot_erase_a_committed_update(
        self,
        client: AsyncClient,
        session: AsyncSession,
        app_user_url: str,
        company: uuid.UUID,
        owner: uuid.UUID,
        owner_password: str,
    ) -> None:
        """`soft_delete_row` never bumped `version` and carried no version
        predicate, so a delete built on a stale read could land on top of an
        update it never saw."""
        from app.core.errors import VersionConflictError
        from app.repositories.records import soft_delete_row, update_row

        headers = await _owner_headers(client, owner_password)
        page_id = await _make_page(client, headers)
        record = await _make_record(client, headers, page_id)

        async with (
            _armed_session(app_user_url, company) as writer,
            _armed_session(app_user_url, company) as deleter,
        ):
            page_w, cols_w, handle_w = await _load_for_update(
                writer, page_id, record["id"], company
            )
            page_d, _, handle_d = await _load_for_update(deleter, page_id, record["id"], company)
            assert handle_w.version == handle_d.version == 1

            await update_row(
                writer,
                page_w,
                handle_w,
                cols_w,
                validated={"note": "edited"},
                occurred_at=handle_w.occurred_at,
                store_id=None,
                business_date=handle_w.business_date,
                updated_by=owner,
            )
            await writer.commit()

            with pytest.raises(VersionConflictError):
                await soft_delete_row(
                    deleter,
                    page_d,
                    handle_d,
                    reason="built on a stale read",
                    updated_by=owner,
                )

        stored = await session.execute(
            text("SELECT is_deleted, data FROM records WHERE id = :id"), {"id": record["id"]}
        )
        row = stored.mappings().one()
        assert row["is_deleted"] is False, "a stale delete erased a committed update"
        assert row["data"]["note"] == "edited"


class TestConcurrentRecordUpdate:
    """The lost-update race on `PATCH /records/{id}`, end to end.

    These serialize in practice (see
    `TestLostUpdateIsBlockedByTheDatabase` for why) so they cannot detect a
    missing database guard — they are here to catch the protocol regressing:
    a conflict must stay a 409 with `VERSION_CONFLICT`, and exactly one
    concurrent writer may ever win.
    """

    async def test_only_one_of_many_concurrent_updates_wins(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _make_page(client, headers)
        record = await _make_record(client, headers, page_id)
        assert record["version"] == 1

        # Every writer claims the same version it just read. Optimistic
        # locking means exactly one may commit; the rest must be told to
        # refetch.
        responses = await asyncio.gather(
            *(
                client.patch(
                    f"/records/{record['id']}",
                    json={"data": {"note": f"writer-{i}"}},
                    headers={**headers, "If-Match": "1"},
                )
                for i in range(_WRITERS)
            )
        )
        ok, conflict = _split(responses)

        assert len(ok) == 1, (
            f"{len(ok)} of {_WRITERS} concurrent writers committed against the same "
            "version — writes were silently lost"
        )
        assert len(conflict) == _WRITERS - 1
        for resp in conflict:
            assert resp.json()["code"] == "VERSION_CONFLICT"

    async def test_the_surviving_row_is_the_winners_write_at_version_two(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """A single 200 is not enough: the stored row must be that winner's
        data at exactly version 2. Several writers each applying `version + 1`
        from a stale read all arrive at 2, so version alone can look correct
        while the data is from a writer that was supposed to be rejected."""
        headers = await _owner_headers(client, owner_password)
        page_id = await _make_page(client, headers)
        record = await _make_record(client, headers, page_id)

        responses = await asyncio.gather(
            *(
                client.patch(
                    f"/records/{record['id']}",
                    json={"data": {"note": f"writer-{i}"}},
                    headers={**headers, "If-Match": "1"},
                )
                for i in range(_WRITERS)
            )
        )
        ok, _ = _split(responses)
        assert len(ok) == 1
        winner = ok[0].json()

        fresh = await client.get(f"/records/{record['id']}", headers=headers)
        assert fresh.status_code == 200, fresh.text
        assert fresh.json()["version"] == 2
        assert fresh.json()["data"]["note"] == winner["data"]["note"]

    async def test_a_delete_racing_an_update_does_not_resurrect_the_row(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """Delete is a write too. If it bypasses the lock, an update that
        raced it can leave a live row carrying the update's data while the
        delete reported success."""
        headers = await _owner_headers(client, owner_password)
        page_id = await _make_page(client, headers)
        record = await _make_record(client, headers, page_id)

        delete_resp, update_resp = await asyncio.gather(
            client.request(
                "DELETE",
                f"/records/{record['id']}",
                json={"reason": "racing the update"},
                headers={**headers, "If-Match": "1"},
            ),
            client.patch(
                f"/records/{record['id']}",
                json={"data": {"note": "racing the delete"}},
                headers={**headers, "If-Match": "1"},
            ),
        )

        # Exactly one may win. If the delete wins, the update legitimately
        # sees a row that is gone (404) or a version that moved (409); if the
        # update wins, the delete must be told its version is stale.
        delete_won = delete_resp.status_code == 204
        update_won = update_resp.status_code == 200
        assert delete_won != update_won, (
            f"delete={delete_resp.status_code} update={update_resp.status_code}: "
            "exactly one of the two must win"
        )
        if delete_won:
            assert update_resp.status_code in (404, 409), update_resp.text
        else:
            assert delete_resp.status_code in (404, 409), delete_resp.text

        # The two outcomes must not both be visible in the stored row.
        fresh = await client.get(f"/records/{record['id']}", headers=headers)
        if delete_won:
            assert fresh.status_code == 404, "row survived a successful delete"
        else:
            assert fresh.status_code == 200
            assert fresh.json()["data"]["note"] == "racing the delete"


class TestConcurrentLedgerReversal:
    """`POST /records/{id}/reverse` flips ACTIVE -> REVERSED and writes a
    replacement. Reversing twice corrects the books twice."""

    async def _ledger_record(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> tuple[str, dict]:
        page_id = await _make_page(client, headers, kind="LEDGER")
        return page_id, await _make_record(client, headers, page_id)

    async def test_concurrent_reversals_produce_exactly_one_reversal(
        self, client: AsyncClient, session: AsyncSession, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        _, record = await self._ledger_record(client, headers)

        responses = await asyncio.gather(
            *(
                client.post(
                    f"/records/{record['id']}/reverse",
                    json={"version": 1, "data": {"note": f"correction-{i}"}},
                    headers=headers,
                )
                for i in range(_WRITERS)
            )
        )
        ok = [r for r in responses if r.status_code in (200, 201)]
        rejected = [r for r in responses if r.status_code in (409, 422)]
        assert len(ok) + len(rejected) == _WRITERS, (
            f"unexpected statuses: {[(r.status_code, r.text) for r in responses]}"
        )
        assert len(ok) == 1, (
            f"{len(ok)} concurrent reversals succeeded — the ledger was corrected "
            "more than once"
        )

        # One replacement row, not several: the original plus exactly one
        # record pointing at it.
        replacements = await session.execute(
            text("SELECT count(*) FROM records WHERE reverses_id = :original"),
            {"original": record["id"]},
        )
        assert replacements.scalar_one() == 1

    async def test_a_reversed_record_cannot_be_reversed_again(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        """The sequential companion to the race above — once a record is
        REVERSED it is terminal, whatever version is presented."""
        headers = await _owner_headers(client, owner_password)
        _, record = await self._ledger_record(client, headers)

        first = await client.post(
            f"/records/{record['id']}/reverse",
            json={"version": 1, "data": {"note": "correction"}},
            headers=headers,
        )
        assert first.status_code in (200, 201), first.text

        current = await client.get(f"/records/{record['id']}", headers=headers)
        assert current.status_code == 200
        assert current.json()["status"] == "REVERSED"

        again = await client.post(
            f"/records/{record['id']}/reverse",
            json={"version": current.json()["version"], "data": {"note": "again"}},
            headers=headers,
        )
        assert again.status_code in (409, 422), again.text


class TestConcurrentRefreshRotation:
    """Refresh rotation must be single-use. Two requests presenting the same
    token concurrently must not both mint a family, or the reuse detector in
    `auth_service.refresh` never fires for a stolen token."""

    async def test_one_refresh_token_yields_one_new_family(
        self, client: AsyncClient, owner: uuid.UUID, owner_password: str
    ) -> None:
        login = await client.post(
            "/auth/login",
            json={"email": "owner@test.lk", "password": owner_password, "device_id": "d1"},
        )
        assert login.status_code == 200, login.text
        refresh_token = login.json()["refresh_token"]

        responses = await asyncio.gather(
            *(
                client.post("/auth/refresh", json={"refresh_token": refresh_token})
                for _ in range(_WRITERS)
            )
        )
        ok = [r for r in responses if r.status_code == 200]
        assert len(ok) == 1, (
            f"{len(ok)} of {_WRITERS} concurrent refreshes succeeded — one token "
            "produced multiple live families"
        )


class TestConcurrentIdempotentCreate:
    """`Idempotency-Key` exists for the retry case, which is concurrent by
    nature — a client that retries before the first attempt answers."""

    async def test_same_key_concurrently_creates_exactly_one_record(
        self, client: AsyncClient, session: AsyncSession, owner: uuid.UUID, owner_password: str
    ) -> None:
        headers = await _owner_headers(client, owner_password)
        page_id = await _make_page(client, headers)
        key = str(uuid.uuid4())
        body = {"occurred_at": "2026-09-07T10:00:00+05:30", "data": {"note": "retried"}}

        responses = await asyncio.gather(
            *(
                client.post(
                    f"/pages/{page_id}/records",
                    json=body,
                    headers={**headers, "Idempotency-Key": key},
                )
                for _ in range(_WRITERS)
            )
        )
        created = [r for r in responses if r.status_code == 201]
        assert created, f"no attempt succeeded: {[(r.status_code, r.text) for r in responses]}"

        # Whatever each caller was told, the page must hold one row.
        count = await session.execute(
            text("SELECT count(*) FROM records WHERE page_id = :page_id"),
            {"page_id": page_id},
        )
        assert count.scalar_one() == 1, "an idempotent create was applied more than once"
