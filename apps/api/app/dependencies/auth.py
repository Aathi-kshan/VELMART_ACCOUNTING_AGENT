"""Authenticated-request dependency (plan section 20.2).

Minimal in P1: verify the token, then re-check `token_version` against the
database so a bumped version invalidates a still-unexpired access token
immediately. P2 replaces the return value with the full `SecurityContext`
(company_id, role, store_ids **and** per-page grants).
"""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.logging import bind_request_context
from app.core.security import TokenError, decode_access_token
from app.db.session import get_session
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


class UnauthenticatedError(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"
    title = "Not authenticated"


async def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None or not credentials.credentials:
        raise UnauthenticatedError("An access token is required.")

    try:
        claims = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise UnauthenticatedError(str(exc)) from exc

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
    return user
