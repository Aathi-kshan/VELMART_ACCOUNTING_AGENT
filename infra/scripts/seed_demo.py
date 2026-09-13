"""Seeds one demo company — a name, an Owner, and the six system pages — so
`register_system_pages` (`app/services/page_service.py`) has a real,
reachable hook to run against (plan section 3.5's registration step). There
is no live `POST /companies` endpoint anywhere in this codebase yet, so this
is the honest way to get a company that has them, until real onboarding
exists.

Run from `apps/api` with `DATABASE_URL` pointed at a Postgres already
migrated to head:

    uv run python ../../infra/scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

# `app.*` imports need apps/api on sys.path when this runs from the repo root
# or from infra/scripts directly, rather than as an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from app.core.context import SecurityContext
from app.core.security import hash_password
from app.db.rls import set_rls_context
from app.db.session import get_sessionmaker
from app.models.user import UserRole
from app.services.page_service import register_system_pages
from sqlalchemy import text

DEMO_COMPANY_NAME = "Velmart Demo Supermarket"
DEMO_OWNER_EMAIL = "owner@velmart-demo.lk"
DEMO_OWNER_PASSWORD = "change-me-now-please"


async def seed_demo() -> uuid.UUID:
    session_factory = get_sessionmaker()
    company_id = uuid.uuid4()
    user_id = uuid.uuid4()

    async with session_factory() as session, session.begin():
        # `companies` carries no `company_id` column of its own, so it's
        # outside RLS (not in migration 0006's TENANT_TABLES) — no context
        # needs to be set before this one insert.
        await session.execute(
            text("INSERT INTO companies (id, name) VALUES (:id, :name)"),
            {"id": str(company_id), "name": DEMO_COMPANY_NAME},
        )

        # `users` *is* RLS-protected, so the new user's own INSERT must
        # already satisfy tenant_isolation's WITH CHECK — set the context to
        # the company just created before it.
        await set_rls_context(session, company_id=company_id, role=UserRole.OWNER.value)
        await session.execute(
            text(
                """
                INSERT INTO users (id, company_id, email, full_name, password_hash, role)
                VALUES (:id, :company_id, :email, 'Demo Owner', :pw, 'OWNER')
                """
            ),
            {
                "id": str(user_id),
                "company_id": str(company_id),
                "email": DEMO_OWNER_EMAIL,
                "pw": hash_password(DEMO_OWNER_PASSWORD),
            },
        )

        ctx = SecurityContext(
            user_id=user_id, company_id=company_id, role=UserRole.OWNER, store_ids=()
        )
        await register_system_pages(session, ctx, company_id)

    print(f"Seeded demo company {company_id} with owner {DEMO_OWNER_EMAIL} / {DEMO_OWNER_PASSWORD}")
    return company_id


if __name__ == "__main__":
    asyncio.run(seed_demo())
