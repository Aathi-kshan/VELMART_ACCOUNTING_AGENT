"""Writing an audit row must not disturb the transaction it is written in.

`write_audit_log` used to call `set_rls_context` on every write. That helper
rewrites **all three** settings (`app.company_id`, `app.role`,
`app.store_ids`), and the audit call passed no `store_ids` — so every audit
write inside a request's transaction silently cleared the store scope for
every query that followed it. It also defaulted to `role="OWNER"` whenever
`actor_role` was omitted, quietly raising the transaction's RLS role.

Audit writes are never the first thing a request does, so the caller has
always armed the context already. `audit_logs` carries `tenant_isolation`
only (migration 0006), so the arming was never needed for the insert itself.

These tests read the settings back out of Postgres directly, because that is
the only place the damage was visible — nothing in the response would show
it, and the failure mode is missing rows rather than an error.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import set_rls_context
from app.services.audit_service import write_audit_log


async def _settings(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(
        text(
            "SELECT current_setting('app.company_id', true) AS company_id, "
            "current_setting('app.role', true) AS role, "
            "current_setting('app.store_ids', true) AS store_ids"
        )
    )
    return dict(result.mappings().one())


class TestRlsContextSurvivesAnAuditWrite:
    async def test_store_ids_are_not_cleared(
        self, app_user_session: AsyncSession, company: uuid.UUID, owner: uuid.UUID
    ) -> None:
        store_ids = (uuid.uuid4(), uuid.uuid4())
        async with app_user_session.begin():
            await set_rls_context(
                app_user_session,
                company_id=company,
                role="MANAGER",
                store_ids=store_ids,
            )
            before = await _settings(app_user_session)

            await write_audit_log(
                app_user_session,
                company_id=company,
                action="RECORD_CREATE",
                entity_type="record",
                entity_id=uuid.uuid4(),
                actor_user_id=owner,
                actor_role="MANAGER",
            )
            after = await _settings(app_user_session)

        assert after["store_ids"] == before["store_ids"], (
            "the audit write cleared the transaction's store scope"
        )
        assert after["store_ids"] == ",".join(str(s) for s in store_ids)

    async def test_the_role_is_not_escalated(
        self, app_user_session: AsyncSession, company: uuid.UUID, owner: uuid.UUID
    ) -> None:
        """`actor_role=None` used to fall back to `"OWNER"`, which for a
        manager's transaction meant `store_scope` stopped applying at all."""
        async with app_user_session.begin():
            await set_rls_context(
                app_user_session, company_id=company, role="MANAGER", store_ids=()
            )
            await write_audit_log(
                app_user_session,
                company_id=company,
                action="RECORD_CREATE",
                entity_type="record",
                entity_id=uuid.uuid4(),
                actor_user_id=owner,
                actor_role=None,
            )
            after = await _settings(app_user_session)

        assert after["role"] == "MANAGER", "the audit write escalated the RLS role"

    async def test_the_audit_row_is_still_written(
        self, app_user_session: AsyncSession, company: uuid.UUID, owner: uuid.UUID
    ) -> None:
        """Not re-arming RLS must not stop the insert from landing."""
        entity_id = uuid.uuid4()
        async with app_user_session.begin():
            await set_rls_context(
                app_user_session, company_id=company, role="OWNER", store_ids=()
            )
            await write_audit_log(
                app_user_session,
                company_id=company,
                action="RECORD_CREATE",
                entity_type="record",
                entity_id=entity_id,
                actor_user_id=owner,
                actor_role="OWNER",
            )

        async with app_user_session.begin():
            await set_rls_context(
                app_user_session, company_id=company, role="OWNER", store_ids=()
            )
            found = await app_user_session.execute(
                text("SELECT count(*) FROM audit_logs WHERE entity_id = :id"),
                {"id": str(entity_id)},
            )
            assert found.scalar_one() == 1


class TestAuditWriteOnASessionWithNoTransaction:
    async def test_it_opens_and_arms_its_own(
        self, app_user_session: AsyncSession, company: uuid.UUID, owner: uuid.UUID
    ) -> None:
        """The path `require_owner` uses: a raw session with no transaction
        and no RLS context. `write_audit_log` must arm it itself, or
        `tenant_isolation` refuses the insert."""
        entity_id = uuid.uuid4()
        assert not app_user_session.in_transaction()

        await write_audit_log(
            app_user_session,
            company_id=company,
            action="PERMISSION_DENIED",
            entity_type="user",
            entity_id=entity_id,
            actor_user_id=owner,
            actor_role="MANAGER",
        )

        async with app_user_session.begin():
            await set_rls_context(
                app_user_session, company_id=company, role="OWNER", store_ids=()
            )
            found = await app_user_session.execute(
                text("SELECT count(*) FROM audit_logs WHERE entity_id = :id"),
                {"id": str(entity_id)},
            )
            assert found.scalar_one() == 1
