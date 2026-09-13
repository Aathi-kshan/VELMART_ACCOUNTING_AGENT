"""Authenticated-request dependency (plan sections 4.2, 20.2).

`current_user` and `security_context` share one internal check:
decode the JWT -> **arm RLS from the token's own claims** -> look up the
fresh `User` row -> verify `is_active` / `token_version`.

RLS must be armed *before* the `User` lookup, not after. `users` is one of
the tables migration 0006 protects with `tenant_isolation`, so a lookup with
no RLS context set returns nothing at all, not "every row" — the policy's
comparison is against an unset (NULL) setting, which never matches. The
token already carries company_id/role/store_ids, signed and therefore
trustworthy, so there is no chicken-and-egg problem here: unlike login (which
has no company yet to scope by), an authenticated request already knows it.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SecurityContext
from app.core.errors import AppError
from app.core.logging import bind_request_context
from app.core.security import AccessTokenClaims, TokenError, decode_access_token
from app.db.rls import set_rls_context
from app.db.session import get_session
from app.models.user import User, UserRole

_bearer = HTTPBearer(auto_error=False)


class UnauthenticatedError(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"
    title = "Not authenticated"


@dataclass(frozen=True, slots=True)
class _Authenticated:
    user: User
    claims: AccessTokenClaims


async def _authenticate(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    session: AsyncSession,
) -> _Authenticated:
    if credentials is None or not credentials.credentials:
        raise UnauthenticatedError("An access token is required.")

    try:
        claims = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise UnauthenticatedError(str(exc)) from exc

    async with session.begin():
        # Armed from the token's own claims — see the module docstring for
        # why this must happen before the User lookup below, not after.
        await set_rls_context(
            session,
            company_id=claims.company_id,
            role=claims.role,
            store_ids=claims.store_ids,
        )
        user = await session.get(User, claims.user_id)

    if user is None or not user.is_active:
        raise UnauthenticatedError("Account is not active.")

    # The check that makes revocation instant: the token carries the version it
    # was minted with, and any bump (role change, deactivation, credential
    # rotation) leaves every outstanding token stale.
    if user.token_version != claims.token_version:
        raise UnauthenticatedError("Session has been invalidated. Please sign in again.")

    request.state.user = user
    bind_request_context(user_id=str(user.id), company_id=str(user.company_id))
    return _Authenticated(user=user, claims=claims)


async def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Used by `/me` — unchanged shape from P1."""
    return (await _authenticate(request, credentials, session)).user


async def security_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> SecurityContext:
    """Used by the guards (app/dependencies/guards.py) and P2's routers.

    Built from the token's claims, not re-derived from the User row, so it
    matches exactly what RLS was armed with a moment ago.
    """
    authed = await _authenticate(request, credentials, session)
    return SecurityContext(
        user_id=authed.claims.user_id,
        company_id=authed.claims.company_id,
        role=UserRole(authed.claims.role),
        store_ids=authed.claims.store_ids,
    )
