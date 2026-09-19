"""User management (plan sections 4.2, 20.2, 21.2). Owner only.

Role changes and deactivation bump `token_version`, which — already proven
correct by P1's `test_token_version` — instantly invalidates every session
that user currently holds, no matter how many devices they're logged in on.

Neither function here commits. Both are only ever called from routers whose
session comes from `app/dependencies/db.py`'s `get_rls_session`, which holds
one transaction open for the whole request and commits it on a clean return
(or rolls it back if anything raises) — a function here calling
`session.commit()` itself would close that transaction out from under the
dependency still holding it open, and the next query on this session would
fail with "Can't operate on closed transaction". This is a different
situation from `auth_service.py`'s login/refresh, which use the plain,
un-wrapped `get_session()` and so must manage their own commit boundaries.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.errors import EmailAlreadyExistsError, ValidationFailedError
from app.core.security import hash_password
from app.models.store import Store
from app.models.user import User, UserRole, UserStore
from app.repositories.base import get_for_company, list_for_company
from app.schemas.user import CreateUserRequest, UpdateUserRequest
from app.services.audit_service import write_audit_log


async def list_users(session: AsyncSession, ctx: SecurityContext) -> list[User]:
    return await list_for_company(session, User, ctx.company_id)


async def _set_store_assignments(
    session: AsyncSession,
    ctx: SecurityContext,
    *,
    user_id: uuid.UUID,
    store_ids: list[uuid.UUID],
) -> None:
    """Replace this user's `user_stores` rows wholesale with `store_ids`.

    Every id is checked against the caller's own company first. `store_ids`
    comes straight from the request body, and `user_stores` has no
    `company_id` column and is deliberately excluded from RLS (migration
    0006), so nothing below this line would have caught an Owner assigning
    one of their managers to another company's store. That id then flows
    into the manager's JWT via `auth_service.store_ids_for` and becomes the
    manager's RLS store scope.
    """
    if store_ids:
        known = await session.execute(
            select(Store.id).where(
                Store.id.in_(store_ids), Store.company_id == ctx.company_id
            )
        )
        unknown = set(store_ids) - {row for (row,) in known.all()}
        if unknown:
            raise ValidationFailedError(
                "store_ids: " + ", ".join(sorted(str(s) for s in unknown)) + " is not a store "
                "in this company."
            )

    await session.execute(delete(UserStore).where(UserStore.user_id == user_id))
    if store_ids:
        await session.execute(
            insert(UserStore),
            [{"user_id": user_id, "store_id": sid} for sid in store_ids],
        )


async def create_user(
    session: AsyncSession, ctx: SecurityContext, payload: CreateUserRequest
) -> User:
    # Fast path: catches the overwhelming majority of duplicates with a
    # clean error before ever touching the insert. `email` is CITEXT, so
    # this comparison is already case-insensitive — no `.lower()` needed.
    existing = await session.execute(
        select(User.id).where(User.company_id == ctx.company_id, User.email == payload.email)
    )
    if existing.scalar_one_or_none() is not None:
        raise EmailAlreadyExistsError("Email is already taken.")

    user = User(
        company_id=ctx.company_id,
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    session.add(user)
    try:
        # Closes the race the pre-check above can't: two requests for the
        # same email can both pass the SELECT before either INSERTs. The
        # UNIQUE (company_id, email) constraint (migration 0001) is the
        # actual source of truth; this just turns its violation into the
        # same clean error instead of an uncaught IntegrityError.
        await session.flush()  # assign user.id before the store rows reference it
    except IntegrityError as exc:
        raise EmailAlreadyExistsError("Email is already taken.") from exc

    if payload.role == UserRole.MANAGER and payload.store_ids:
        await _set_store_assignments(session, ctx, user_id=user.id, store_ids=payload.store_ids)

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="USER_CREATE",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        new_data={
            "email": payload.email,
            "full_name": payload.full_name,
            "role": payload.role.value,
        },
    )
    return user


async def update_user(
    session: AsyncSession,
    ctx: SecurityContext,
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
) -> User | None:
    """Returns None if `user_id` doesn't exist in this company — the caller
    (the router) turns that into a 404, never a 403; a manager should not be
    able to tell "wrong company" apart from "no such user" (plan section 20.2's
    non-enumeration principle applies here too)."""
    user = await get_for_company(session, User, user_id, ctx.company_id)
    if user is None:
        return None

    old_data = {"full_name": user.full_name, "role": user.role.value, "is_active": user.is_active}
    values: dict[str, object] = {}
    security_sensitive = False

    if payload.full_name is not None:
        values["full_name"] = payload.full_name
    if payload.role is not None and payload.role != user.role:
        values["role"] = payload.role
        security_sensitive = True
    if payload.is_active is not None and payload.is_active != user.is_active:
        values["is_active"] = payload.is_active
        security_sensitive = True

    if security_sensitive:
        values["token_version"] = user.token_version + 1

    if values:
        await session.execute(update(User).where(User.id == user.id).values(**values))
        await session.refresh(user)

    if payload.store_ids is not None:
        await _set_store_assignments(session, ctx, user_id=user.id, store_ids=payload.store_ids)

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="USER_UPDATE",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        old_data=old_data,
        new_data={
            "full_name": user.full_name,
            "role": user.role.value,
            "is_active": user.is_active,
        },
    )
    return user
