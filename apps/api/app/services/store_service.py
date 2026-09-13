"""Store management (plan sections 4.2, 4.5, 21.2).

`list_stores` is the 🟡 filtered case from plan section 4.2: an owner sees
every store in the company, a manager only the stores `user_stores` assigns
them to — never a 403. `create_store`/`update_store` are owner-only, gated by
`require_owner` in the router, not here.

Neither writer here commits — see user_service.py's module docstring for why:
their routers all use `get_rls_session`, which owns one transaction for the
whole request.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.models.store import Store
from app.models.user import UserStore
from app.repositories.base import get_for_company, list_for_company
from app.schemas.store import CreateStoreRequest, UpdateStoreRequest
from app.services.audit_service import write_audit_log


async def list_stores(session: AsyncSession, ctx: SecurityContext) -> list[Store]:
    if ctx.is_owner:
        return await list_for_company(session, Store, ctx.company_id)

    result = await session.execute(
        select(Store)
        .join(UserStore, UserStore.store_id == Store.id)
        .where(UserStore.user_id == ctx.user_id, Store.company_id == ctx.company_id)
    )
    return list(result.scalars().all())


async def create_store(
    session: AsyncSession, ctx: SecurityContext, payload: CreateStoreRequest
) -> Store:
    store = Store(
        company_id=ctx.company_id,
        code=payload.code,
        name=payload.name,
        address=payload.address,
    )
    session.add(store)
    await session.flush()

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="STORE_CREATE",
        entity_type="store",
        entity_id=store.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        new_data={"code": payload.code, "name": payload.name, "address": payload.address},
    )
    return store


async def update_store(
    session: AsyncSession,
    ctx: SecurityContext,
    store_id: uuid.UUID,
    payload: UpdateStoreRequest,
) -> Store | None:
    """Returns None if `store_id` doesn't exist in this company — the router
    turns that into a 404 (same non-enumeration reasoning as user_service.py's
    update_user)."""
    store = await get_for_company(session, Store, store_id, ctx.company_id)
    if store is None:
        return None

    old_data = {"name": store.name, "address": store.address, "is_active": store.is_active}
    values: dict[str, object] = {}
    if payload.name is not None:
        values["name"] = payload.name
    if payload.address is not None:
        values["address"] = payload.address
    if payload.is_active is not None:
        values["is_active"] = payload.is_active

    if values:
        await session.execute(update(Store).where(Store.id == store.id).values(**values))
        await session.refresh(store)

    await write_audit_log(
        session,
        company_id=ctx.company_id,
        action="STORE_UPDATE",
        entity_type="store",
        entity_id=store.id,
        actor_user_id=ctx.user_id,
        actor_role=ctx.role.value,
        old_data=old_data,
        new_data={"name": store.name, "address": store.address, "is_active": store.is_active},
    )
    return store
