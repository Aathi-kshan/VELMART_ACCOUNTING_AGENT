"""User management endpoints (plan sections 4.2, 21.2). Owner only.

Thin: every route just unwraps the request, delegates to
`app/services/user_service.py`, and shapes the response. `require_owner`
(app/dependencies/guards.py) is the single gate — see that module for why a
denial is audited before the 403 is raised.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.errors import NotFoundError
from app.dependencies.db import get_rls_session
from app.dependencies.guards import require_owner
from app.models.user import User
from app.schemas.auth import UserOut
from app.schemas.user import CreateUserRequest, UpdateUserRequest
from app.services import auth_service, user_service

router = APIRouter(tags=["users"])


async def _user_out(session: AsyncSession, user: User) -> UserOut:
    store_ids = await auth_service.store_ids_for(session, user)
    return UserOut(
        id=user.id,
        company_id=user.company_id,
        full_name=user.full_name,
        email=str(user.email),
        role=str(user.role),
        is_active=user.is_active,
        store_ids=store_ids,
    )


@router.get("/users", response_model=list[UserOut])
async def list_users(
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> list[UserOut]:
    users = await user_service.list_users(session, ctx)
    return [await _user_out(session, u) for u in users]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    payload: CreateUserRequest,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> UserOut:
    user = await user_service.create_user(session, ctx, payload)
    return await _user_out(session, user)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    ctx: SecurityContext = Depends(require_owner),
    session: AsyncSession = Depends(get_rls_session),
) -> UserOut:
    user = await user_service.update_user(session, ctx, user_id, payload)
    if user is None:
        raise NotFoundError("No such user.")
    return await _user_out(session, user)
