"""Password hashing and JWT handling (plan sections 20.2, 20.3).

Argon2id at m=64MB, t=3, p=4. Access tokens are short-lived (15 min) and carry
`token_version`, so bumping `users.token_version` invalidates every session for
that user instantly — which is what happens when a role changes or an account is
deactivated.

Refresh tokens are never stored in the clear: only their SHA-256 digest is kept,
so a database leak does not hand over live sessions.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

from app.config import get_settings

#: Plan section 20.3: Argon2id, m=64MB, t=3, p=4.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,  # KiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

#: Plan section 20.3: minimum 10-character passwords.
MIN_PASSWORD_LENGTH = 10

TokenType = Literal["access"]


class TokenError(Exception):
    """A token was missing, malformed, expired, or otherwise unusable."""


# --- passwords --------------------------------------------------------------


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verification. Never raises on a wrong password."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when a stored hash predates the current Argon2 parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# --- access tokens ----------------------------------------------------------


def create_access_token(
    *,
    user_id: uuid.UUID,
    company_id: uuid.UUID,
    role: str,
    store_ids: list[uuid.UUID] | None = None,
    token_version: int,
) -> tuple[str, datetime]:
    """Mint an access JWT. Returns the token and its expiry.

    Claims are exactly those in plan section 20.2. Page grants are deliberately
    **not** in the token — they are read per request, so revoking a grant takes
    effect immediately rather than at the next token refresh.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "company_id": str(company_id),
        "role": role,
        "store_ids": [str(s) for s in (store_ids or [])],
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "token_version": token_version,
        "typ": "access",
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify signature and expiry, and return the claims.

    The algorithm is pinned to the configured one: accepting whatever the token
    header asks for is how `alg: none` and HS/RS confusion attacks work.
    """
    settings = get_settings()
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("token is invalid") from exc

    if claims.get("typ") != "access":
        raise TokenError("not an access token")
    return claims


# --- refresh tokens ---------------------------------------------------------


def generate_refresh_token() -> str:
    """A high-entropy opaque token. Only its digest is ever persisted."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """SHA-256 of the raw token — what goes in `refresh_tokens.token_hash`.

    Fast digest rather than Argon2 deliberately: the token is already 48 bytes
    of CSPRNG output, so it needs no stretching, and lookup happens on every
    refresh.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=get_settings().REFRESH_TOKEN_DAYS)
