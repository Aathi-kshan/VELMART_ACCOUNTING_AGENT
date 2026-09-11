"""Auth endpoints (plan section 20.2, docs/API.md section 3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.ratelimit import hit_login_ip
from app.db.session import get_session
from app.dependencies.auth import current_user
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
    UserOut,
)
from app.services import auth_service

router = APIRouter(tags=["auth"])


class InvalidCredentialsError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "INVALID_CREDENTIALS"
    title = "Invalid credentials"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMITED"
    title = "Too many requests"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _token_response(session: AsyncSession, pair: auth_service.TokenPair) -> TokenResponse:
    store_ids = await auth_service.store_ids_for(session, pair.user)
    return TokenResponse(
        access_token=pair.access_token,
        expires_in=pair.expires_in,
        refresh_token=pair.refresh_token,
        user=UserOut(
            id=pair.user.id,
            company_id=pair.user.company_id,
            full_name=pair.user.full_name,
            email=str(pair.user.email),
            role=str(pair.user.role),
            store_ids=store_ids,
        ),
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    ip = _client_ip(request)

    # Throttle before touching the password path at all (plan section 20.3:
    # 5 logins/min/IP), so brute force is bounded regardless of the account.
    async with session.begin():
        limit = await hit_login_ip(session, ip)
    if not limit.allowed:
        raise RateLimitedError(
            "Too many login attempts. Please wait and try again.",
            headers={"Retry-After": str(limit.retry_after_seconds)},
        )

    # auth_service.login manages its own commit boundaries — it commits the
    # failure bookkeeping (attempt counter, audit row) before raising, so a
    # transaction wrapper here would roll that back the moment the exception
    # propagates. See the module docstring in auth_service.py.
    try:
        pair = await auth_service.login(
            session,
            email=str(payload.email),
            password=payload.password,
            device_id=payload.device_id,
            device_name=payload.device_name,
            ip_address=ip,
            user_agent=request.headers.get("user-agent"),
        )
    except auth_service.AuthenticationError as exc:
        # One message for every failure mode — wrong password, unknown email,
        # locked account — so the endpoint cannot enumerate users.
        raise InvalidCredentialsError(str(exc)) from exc
    return await _token_response(session, pair)


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    # Same reasoning as login(): auth_service.refresh commits before raising
    # on token reuse, because revoking the device family must survive even
    # though the request itself is about to fail.
    try:
        pair = await auth_service.refresh(
            session,
            refresh_token=payload.refresh_token,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except auth_service.RefreshTokenError as exc:
        raise InvalidCredentialsError(str(exc)) from exc
    return await _token_response(session, pair)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: LogoutRequest, session: AsyncSession = Depends(get_session)) -> Response:
    await auth_service.logout(session, refresh_token=payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
async def me(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> UserOut:
    # Store assignments (and, from P3, page grants) are read per request rather
    # than carried in the token, so a revocation takes effect immediately.
    store_ids = await auth_service.store_ids_for(session, user)
    return UserOut(
        id=user.id,
        company_id=user.company_id,
        full_name=user.full_name,
        email=str(user.email),
        role=str(user.role),
        store_ids=store_ids,
    )
