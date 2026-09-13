"""Store endpoints (plan sections 4.2, 4.5, 21.2).

`GET /stores` is the 🟡 filtered case — any authenticated role, but scoped by
`store_service.list_stores` rather than gated by `require_owner`. `POST` and
`PATCH` are owner-only.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.errors import NotFoundError
from app.dependencies.auth import security_context
from app.dependencies.db import get_rls_session
from app.dependencies.guards import require_owner
from app.schemas.store import CreateStoreRequest, StoreOut, UpdateStoreRequest
from app.services import store_service

router = APIRouter(tags=["stores"])


@router.get("/stores", response_model=list[StoreOut])
async def list_stores(
    ctx: SecurityContext = Depends(security_context),
    session: AsyncSession = Depends(get_rls_session),
) -> list[StoreOut]:
    stores = await store_service.list_stores(session, ctx)
    return [StoreOut.model_validate(s) for s in stores]


@router.post("/stores", response_model=StoreOut, status_code=201)
async def create_store(
    payload: CreateStoreRequest,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> StoreOut:
    store = await store_service.create_store(session, ctx, payload)
    return StoreOut.model_validate(store)


@router.patch("/stores/{store_id}", response_model=StoreOut)
async def update_store(
    store_id: uuid.UUID,
    payload: UpdateStoreRequest,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> StoreOut:
    store = await store_service.update_store(session, ctx, store_id, payload)
    if store is None:
        raise NotFoundError("No such store.")
    return StoreOut.model_validate(store)
