"""Provision a company: its Owner and the six system pages.

There is still no `POST /companies` endpoint, so this script is the only way
a company comes into existence — which made its previous form a problem. It
hardcoded one demo company name, owner email and password, so onboarding a
real second company meant editing the source, and a company that somehow
already existed *without* its system pages could not be repaired at all.

That was not hypothetical: the development database held a company with
**zero pages** beside the demo one with eight. Every system page is seeded by
`register_system_pages`, and a company that never had it run against it gets
an empty, unusable app with no supported way to fix it.

So this now does three things, all idempotent:

    # provision a new company
    uv run python ../../infra/scripts/seed_demo.py \\
        --name "Kandy Test Traders" --owner-email owner@kandy.lk --password '...'

    # the original demo company, unchanged defaults
    uv run python ../../infra/scripts/seed_demo.py --demo

    # give every existing company any system pages it is missing
    uv run python ../../infra/scripts/seed_demo.py --repair-all

Run from `apps/api` with `DATABASE_URL` pointed at a database migrated to
head. Re-running is safe: `register_system_pages` skips keys that already
exist, and an existing company or owner email is reused rather than
duplicated.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

# `app.*` imports need apps/api on sys.path when this runs from the repo root
# or from infra/scripts directly, rather than as an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.security import hash_password
from app.db.rls import set_rls_context
from app.db.session import get_sessionmaker
from app.models.user import UserRole
from app.services.page_service import register_system_pages

DEMO_COMPANY_NAME = "Velmart Demo Supermarket"
DEMO_OWNER_EMAIL = "owner@velmart-demo.lk"
DEMO_OWNER_PASSWORD = "change-me-now-please"  # noqa: S105 - demo placeholder, printed on use


async def _ensure_company(session: AsyncSession, name: str) -> uuid.UUID:
    """Return the existing company with this name, or create it."""
    existing = await session.scalar(
        text("SELECT id FROM companies WHERE name = :name"), {"name": name}
    )
    if existing is not None:
        return uuid.UUID(str(existing))

    company_id = uuid.uuid4()
    # `companies` carries no `company_id` column of its own, so it sits
    # outside RLS (not in migration 0006's TENANT_TABLES) — no context needs
    # to be set before this one insert.
    await session.execute(
        text("INSERT INTO companies (id, name) VALUES (:id, :name)"),
        {"id": str(company_id), "name": name},
    )
    return company_id


async def _ensure_owner(
    session: AsyncSession, company_id: uuid.UUID, email: str, password: str
) -> uuid.UUID:
    """Return this company's existing owner with that email, or create one."""
    # `users` *is* RLS-protected, so the context must be armed before both the
    # lookup and the insert, or the SELECT returns nothing and the INSERT is
    # refused by tenant_isolation's WITH CHECK.
    await set_rls_context(session, company_id=company_id, role=UserRole.OWNER.value)

    existing = await session.scalar(
        text("SELECT id FROM users WHERE company_id = :company_id AND email = :email"),
        {"company_id": str(company_id), "email": email},
    )
    if existing is not None:
        return uuid.UUID(str(existing))

    user_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO users (id, company_id, email, full_name, password_hash, role)
            VALUES (:id, :company_id, :email, 'Owner', :pw, 'OWNER')
            """
        ),
        {
            "id": str(user_id),
            "company_id": str(company_id),
            "email": email,
            "pw": hash_password(password),
        },
    )
    return user_id


async def provision(name: str, owner_email: str, password: str) -> uuid.UUID:
    session_factory = get_sessionmaker()
    async with session_factory() as session, session.begin():
        company_id = await _ensure_company(session, name)
        user_id = await _ensure_owner(session, company_id, owner_email, password)
        ctx = SecurityContext(
            user_id=user_id, company_id=company_id, role=UserRole.OWNER, store_ids=()
        )
        await register_system_pages(session, ctx, company_id)

    print(f"Provisioned {name} ({company_id}) with owner {owner_email}")
    return company_id


async def repair_all() -> int:
    """Give every existing company any system pages it is missing.

    The repair path that did not exist. A company created outside this script
    — as one in the development database was — has no pages at all, and
    nothing in the application will ever create them.
    """
    session_factory = get_sessionmaker()
    repaired = 0

    # Read the inventory in its own session and finish with it before doing
    # any writing. SQLAlchemy autobegins a transaction on the first query, so
    # opening `session.begin()` afterwards on the same session raises
    # "A transaction is already begun"; a session per phase keeps each
    # company's repair in its own transaction as intended.
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT c.id, c.name, count(p.id) AS pages
                    FROM companies c
                    LEFT JOIN pages p ON p.company_id = c.id
                    GROUP BY c.id, c.name
                    ORDER BY c.name
                    """
                )
            )
        ).all()

    for raw_company_id, company_name, page_count in rows:
        company_id = uuid.UUID(str(raw_company_id))
        async with session_factory() as session, session.begin():
            # `users` and `pages` are both RLS-protected, so the context has
            # to be armed before the owner lookup as well as the insert —
            # without it the SELECT silently returns nothing.
            await set_rls_context(session, company_id=company_id, role=UserRole.OWNER.value)

            owner_id = await session.scalar(
                text(
                    "SELECT id FROM users WHERE company_id = :cid AND role = 'OWNER' "
                    "ORDER BY created_at LIMIT 1"
                ),
                {"cid": str(company_id)},
            )
            if owner_id is None:
                print(f"  SKIP {company_name}: no Owner to attribute the pages to")
                continue

            ctx = SecurityContext(
                user_id=uuid.UUID(str(owner_id)),
                company_id=company_id,
                role=UserRole.OWNER,
                store_ids=(),
            )
            await register_system_pages(session, ctx, company_id)

        # Re-count in a fresh transaction, with the context armed again —
        # `pages` is RLS-protected, so an unarmed count reads zero and would
        # report every repair as having done nothing.
        async with session_factory() as session, session.begin():
            await set_rls_context(session, company_id=company_id, role=UserRole.OWNER.value)
            after = await session.scalar(
                text("SELECT count(*) FROM pages WHERE company_id = :cid"),
                {"cid": str(company_id)},
            )
        added = int(after or 0) - int(page_count)
        status = f"added {added}" if added else "already complete"
        print(f"  {company_name}: {page_count} -> {after} pages ({status})")
        repaired += 1 if added else 0

    print(f"Repaired {repaired} company/companies")
    return repaired


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", help="Company name to provision")
    parser.add_argument("--owner-email", help="Owner's email address")
    parser.add_argument("--password", help="Owner's initial password")
    parser.add_argument(
        "--demo", action="store_true", help="Provision the built-in demo company"
    )
    parser.add_argument(
        "--repair-all",
        action="store_true",
        help="Give every existing company any system pages it is missing",
    )
    args = parser.parse_args()

    if args.repair_all:
        asyncio.run(repair_all())
        return 0

    if args.demo:
        asyncio.run(provision(DEMO_COMPANY_NAME, DEMO_OWNER_EMAIL, DEMO_OWNER_PASSWORD))
        print(f"  password: {DEMO_OWNER_PASSWORD}")
        return 0

    if not (args.name and args.owner_email and args.password):
        parser.error("provide --name, --owner-email and --password, or use --demo/--repair-all")

    asyncio.run(provision(args.name, args.owner_email, args.password))
    return 0


if __name__ == "__main__":
    sys.exit(main())
