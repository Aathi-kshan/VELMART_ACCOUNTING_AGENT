"""Password hashing and JWTs (plan sections 20.2, 20.3).

Argon2id at m=64MB, t=3, p=4. Access tokens are short (15 min) and carry
`token_version`, so bumping `users.token_version` invalidates every session for
that user instantly — which is what happens when a role changes or an account is
deactivated.

Page grants are deliberately **not** in the token: they are read per request, so
revoking a grant takes effect immediately rather than at the next refresh.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.config import get_settings

#: Plan section 20.3: Argon2id, m=64MB, t=3, p=4.
_hasher = PasswordHasher(
    memory_cost=65536,  # 64 MiB
    time_cost=3,
    parallelism=4,
    type=Type.ID,
)

#: Plan section 20.3: minimum 10-character passwords.
MIN_PASSWORD_LENGTH = 10


class TokenError(Exception):
    """Raised when an access token is missing, malformed, or expired."""


class WeakPasswordError(ValueError):
    """Raised when a password does not meet the minimum policy."""


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------


def validate_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")


def hash_password(password: str) -> str:
    validate_password_strength(password)
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verify. Returns False rather than raising on mismatch."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when a stored hash predates the current Argon2 parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return False


# --------------------------------------------------------------------------
# Access tokens
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """The verified contents of an access token (plan section 20.2)."""

    user_id: uuid.UUID
    company_id: uuid.UUID
    role: str
    store_ids: tuple[uuid.UUID, ...]
    token_version: int
    jti: str


def create_access_token(
    *,
    user_id: uuid.UUID,
    company_id: uuid.UUID,
    role: str,
    store_ids: list[uuid.UUID] | tuple[uuid.UUID, ...] = (),
    token_version: int,
) -> str:
    settings = get_settings()
    now = datetime.now(tz=UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "company_id": str(company_id),
        "role": role,
        "store_ids": [str(s) for s in store_ids],
        "token_version": token_version,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> AccessTokenClaims:
    """Verify signature and expiry, and return the claims.

    Does **not** check `token_version` against the database — that is a
    per-request read (app/dependencies/auth.py), because the whole point is
    that it can change between token issue and token use.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Access token is invalid.") from exc

    try:
        return AccessTokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            company_id=uuid.UUID(payload["company_id"]),
            role=payload["role"],
            store_ids=tuple(uuid.UUID(s) for s in payload.get("store_ids", [])),
            token_version=int(payload["token_version"]),
            jti=payload["jti"],
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise TokenError("Access token is missing required claims.") from exc


# --------------------------------------------------------------------------
# Refresh tokens
# --------------------------------------------------------------------------


def generate_refresh_token() -> str:
    """The raw value handed to the client. Never stored."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """What goes in `refresh_tokens.token_hash` (plan section 8.2).

    sha256 rather than Argon2: this is a 48-byte random value, not a
    human-chosen password, so there is nothing to brute-force and the lookup
    happens on every refresh.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
