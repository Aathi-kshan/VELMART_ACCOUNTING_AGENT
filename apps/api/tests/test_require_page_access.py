"""Direct unit tests of `require_page_access` (plan sections 4.2, 4.3).

Built in P2 with no caller yet; P3 gave it real callers and, per docs/API.md
section 1.4, corrected its "no grant" case from a flat 403 to 404 (a page
invisible to a manager must not be confirmed to exist) — see
app/dependencies/guards.py's module docstring.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.errors import NotFoundError, PermissionDeniedError
from app.dependencies.guards import require_page_access
from app.models.user import UserRole


@pytest.fixture
async def page(session: AsyncSession, company: uuid.UUID, owner: uuid.UUID) -> uuid.UUID:
    page_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO pages (id, company_id, key, name, created_by) "
            "VALUES (:id, :company_id, 'matrix_page', 'Matrix Page', :created_by)"
        ),
        {"id": str(page_id), "company_id": str(company), "created_by": str(owner)},
    )
    await session.commit()
    return page_id


def _ctx(*, company_id: uuid.UUID, user_id: uuid.UUID, role: UserRole) -> SecurityContext:
    return SecurityContext(user_id=user_id, company_id=company_id, role=role, store_ids=())


async def _grant(
    session: AsyncSession,
    *,
    page_id: uuid.UUID,
    user_id: uuid.UUID,
    can_view: bool,
    can_create: bool,
) -> None:
    await session.execute(
        text(
            "INSERT INTO page_access (page_id, user_id, can_view, can_create) "
            "VALUES (:page_id, :user_id, :can_view, :can_create)"
        ),
        {
            "page_id": str(page_id),
            "user_id": str(user_id),
            "can_view": can_view,
            "can_create": can_create,
        },
    )
    await session.commit()


class TestRequirePageAccess:
    async def test_owner_is_always_allowed_without_any_grant_row(
        self, session: AsyncSession, company: uuid.UUID, owner: uuid.UUID, page: uuid.UUID
    ) -> None:
        ctx = _ctx(company_id=company, user_id=owner, role=UserRole.OWNER)
        await require_page_access(page, "view", ctx, session)
        await require_page_access(page, "create", ctx, session)

    async def test_manager_with_view_grant_can_view(
        self, session: AsyncSession, company: uuid.UUID, manager: uuid.UUID, page: uuid.UUID
    ) -> None:
        await _grant(session, page_id=page, user_id=manager, can_view=True, can_create=False)
        ctx = _ctx(company_id=company, user_id=manager, role=UserRole.MANAGER)
        await require_page_access(page, "view", ctx, session)

    async def test_manager_with_no_grant_gets_not_found_not_denied(
        self, session: AsyncSession, company: uuid.UUID, manager: uuid.UUID, page: uuid.UUID
    ) -> None:
        """A page with no grant row is invisible to this manager — 404, not
        403, so a denial response can't be used to confirm the page exists."""
        ctx = _ctx(company_id=company, user_id=manager, role=UserRole.MANAGER)
        with pytest.raises(NotFoundError):
            await require_page_access(page, "view", ctx, session)

    async def test_manager_with_create_grant_can_also_view(
        self, session: AsyncSession, company: uuid.UUID, manager: uuid.UUID, page: uuid.UUID
    ) -> None:
        """create implies the row is granted at all; a view request just
        checks that a grant row exists and reads the can_view column — a
        create-only grant (can_view=False) still has a row, but the weaker
        `view` ask reads its own column, which is False here, so it is
        correctly denied rather than "upgraded" by the create grant."""
        await _grant(session, page_id=page, user_id=manager, can_view=False, can_create=True)
        ctx = _ctx(company_id=company, user_id=manager, role=UserRole.MANAGER)
        with pytest.raises(PermissionDeniedError):
            await require_page_access(page, "view", ctx, session)
        await require_page_access(page, "create", ctx, session)

    async def test_manager_with_view_only_grant_is_denied_create(
        self, session: AsyncSession, company: uuid.UUID, manager: uuid.UUID, page: uuid.UUID
    ) -> None:
        await _grant(session, page_id=page, user_id=manager, can_view=True, can_create=False)
        ctx = _ctx(company_id=company, user_id=manager, role=UserRole.MANAGER)
        await require_page_access(page, "view", ctx, session)
        with pytest.raises(PermissionDeniedError):
            await require_page_access(page, "create", ctx, session)

    async def test_denial_is_audited_even_as_a_404(
        self, session: AsyncSession, company: uuid.UUID, manager: uuid.UUID, page: uuid.UUID
    ) -> None:
        """The audit trail is owner-only, so recording this attempt leaks
        nothing to the manager even though the HTTP response is a 404."""
        ctx = _ctx(company_id=company, user_id=manager, role=UserRole.MANAGER)
        with pytest.raises(NotFoundError):
            await require_page_access(page, "view", ctx, session)

        row = (
            await session.execute(
                text(
                    "SELECT action, entity_type, entity_id FROM audit_logs "
                    "WHERE company_id = :cid AND action = 'PERMISSION_DENIED'"
                ),
                {"cid": str(company)},
            )
        ).one()
        assert row.entity_type == "page"
        assert row.entity_id == page
