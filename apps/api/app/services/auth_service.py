"""Authentication (plan section 20.2).

Login → Argon2id verify → access JWT (15 min) + a device-bound refresh token
(30 days, stored only as a sha256 hash).

Refresh **rotates**: the presented token is revoked, a new one issued, and
`replaced_by` links them. Presenting an already-revoked token means the token
leaked and is being replayed, so the whole device family is revoked and the
event is audited.

Failed logins are deliberately indistinguishable from unknown emails — the same
generic 401, so the endpoint cannot be used to enumerate users.

Every function here commits its own writes before returning **or raising**.
A caller wrapping these calls in its own `session.begin()` block would roll
back the failure bookkeeping (the incremented `failed_attempts`, the
`LOGIN_FAILED` audit row, the device-family revocation on token reuse) the
moment the corresponding exception propagates out of that block — silently
disabling lockout and, worse, silently un-revoking a token that was just
identified as stolen. Committing here, before every raise, is what makes
that bookkeeping durable regardless of what the caller does with the error.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    verify_password,
)
from app.db.rls import set_rls_context
from app.models.user import RefreshToken, User

log = get_logger(__name__)

#: Plan section 20.2: lock the account for 15 minutes after 5 failed attempts.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


class AuthenticationError(Exception):
    """Login failed. The message is deliberately generic (no enumeration)."""


class AccountLockedError(AuthenticationError):
    """Too many failed attempts."""


class RefreshTokenError(Exception):
    """The refresh token is unknown, expired, or already revoked."""


class TokenReuseError(RefreshTokenError):
    """A revoked token was replayed — treated as theft."""


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    user: User


async def store_ids_for(session: AsyncSession, user: User) -> list[uuid.UUID]:
    """Assigned stores. Owners implicitly have every store (plan section 4.5)."""
    if user.role == "OWNER":
        result = await session.execute(
            text("SELECT id FROM stores WHERE company_id = :cid AND is_active"),
            {"cid": str(user.company_id)},
        )
    else:
        result = await session.execute(
            text("SELECT store_id FROM user_stores WHERE user_id = :uid"),
            {"uid": str(user.id)},
        )
    return [row[0] for row in result.all()]


async def _issue_tokens(
    session: AsyncSession, user: User, *, device_id: str, device_name: str | None
) -> TokenPair:
    settings = get_settings()
    store_ids = await store_ids_for(session, user)

    raw_refresh = generate_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            device_id=device_id,
            device_name=device_name,
            expires_at=datetime.now(tz=UTC) + timedelta(days=settings.REFRESH_TOKEN_DAYS),
        )
    )

    access = create_access_token(
        user_id=user.id,
        company_id=user.company_id,
        role=str(user.role),
        store_ids=store_ids,
        token_version=user.token_version,
    )
    return TokenPair(
        access_token=access,
        refresh_token=raw_refresh,
        expires_in=settings.ACCESS_TOKEN_MINUTES * 60,
        user=user,
    )


async def _audit(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    action: str,
    actor_user_id: uuid.UUID | None,
    actor_role: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    """Write an audit row.

    RLS applies to app_user, so the tenant context must be set inside this
    transaction first or the insert is refused by the tenant_isolation policy.
    `row_hash` is computed by the database trigger, never here.
    """
    await set_rls_context(session, company_id=company_id, role=actor_role or "OWNER")
    await session.execute(
        text(
            """
            INSERT INTO audit_logs
                (company_id, actor_user_id, actor_role, action, entity_type,
                 entity_id, source, ip_address, user_agent, row_hash)
            VALUES
                (:company_id, :actor_user_id, CAST(:actor_role AS user_role), :action,
                 'user', :entity_id, 'APP', CAST(:ip AS inet), :ua, '')
            """
        ),
        {
            "company_id": str(company_id),
            "actor_user_id": str(actor_user_id) if actor_user_id else None,
            "actor_role": actor_role,
            "action": action,
            "entity_id": str(actor_user_id) if actor_user_id else None,
            "ip": ip_address,
            "ua": user_agent,
        },
    )


async def login(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    device_id: str,
    device_name: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TokenPair:
    """Authenticate and issue a token pair.

    Every failure path raises the same `AuthenticationError` message.
    """
    # `users` is UNIQUE (company_id, email) — email is unique only *within* a
    # company, but section 20.2's login payload carries no company. V1 has one
    # company, so an exact single match is required; multi-company would need
    # globally unique emails or a company selector.
    result = await session.execute(select(User).where(User.email == email))
    users = result.scalars().all()
    user = users[0] if len(users) == 1 else None

    if user is None:
        # No company to attribute an audit row to, so this is logged only.
        log.warning("auth.login_unknown_email", ip_address=ip_address)
        raise AuthenticationError("Invalid email or password.")

    now = datetime.now(tz=UTC)

    if user.locked_until is not None and user.locked_until > now:
        await _audit(
            session,
            company_id=user.company_id,
            action="LOGIN_FAILED",
            actor_user_id=user.id,
            actor_role=str(user.role),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await session.commit()
        raise AccountLockedError("Invalid email or password.")

    if not user.is_active or not verify_password(password, user.password_hash):
        attempts = user.failed_attempts + 1
        locked_until = (
            now + timedelta(minutes=LOCKOUT_MINUTES) if attempts >= MAX_FAILED_ATTEMPTS else None
        )
        await session.execute(
            update(User)
            .where(User.id == user.id)
            .values(failed_attempts=attempts, locked_until=locked_until)
        )
        await _audit(
            session,
            company_id=user.company_id,
            action="LOGIN_FAILED",
            actor_user_id=user.id,
            actor_role=str(user.role),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        log.warning(
            "auth.login_failed",
            user_id=str(user.id),
            failed_attempts=attempts,
            locked=locked_until is not None,
        )
        await session.commit()
        raise AuthenticationError("Invalid email or password.")

    # Success: clear the counter and refresh the stored hash if the Argon2
    # parameters have moved on since it was written.
    values: dict[str, object] = {
        "failed_attempts": 0,
        "locked_until": None,
        "last_login_at": now,
    }
    if needs_rehash(user.password_hash):
        values["password_hash"] = hash_password(password)
    await session.execute(update(User).where(User.id == user.id).values(**values))

    pair = await _issue_tokens(session, user, device_id=device_id, device_name=device_name)
    await _audit(
        session,
        company_id=user.company_id,
        action="LOGIN",
        actor_user_id=user.id,
        actor_role=str(user.role),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    log.info("auth.login_ok", user_id=str(user.id), role=str(user.role))
    await session.commit()
    return pair


async def refresh(
    session: AsyncSession,
    *,
    refresh_token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TokenPair:
    """Rotate a refresh token, detecting replay of a revoked one."""
    token_hash = hash_refresh_token(refresh_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()

    if stored is None:
        raise RefreshTokenError("Invalid refresh token.")

    now = datetime.now(tz=UTC)

    if stored.revoked_at is not None:
        # This token was already rotated away. Someone is replaying an old
        # value, so assume the device is compromised and revoke every token
        # issued to it (plan section 20.2). This revocation MUST be durable
        # even though the request is about to fail — commit before raising.
        await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == stored.user_id,
                RefreshToken.device_id == stored.device_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        user = await session.get(User, stored.user_id)
        if user is not None:
            await _audit(
                session,
                company_id=user.company_id,
                action="LOGIN_FAILED",
                actor_user_id=user.id,
                actor_role=str(user.role),
                ip_address=ip_address,
                user_agent=user_agent,
            )
        log.error(
            "auth.refresh_token_reuse",
            user_id=str(stored.user_id),
            device_id=stored.device_id,
        )
        await session.commit()
        raise TokenReuseError("Refresh token has been revoked.")

    if stored.expires_at <= now:
        raise RefreshTokenError("Refresh token has expired.")

    user = await session.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise RefreshTokenError("Invalid refresh token.")

    pair = await _issue_tokens(
        session, user, device_id=stored.device_id, device_name=stored.device_name
    )
    await session.flush()  # assign the new token's id before linking to it

    new_hash = hash_refresh_token(pair.refresh_token)
    new_result = await session.execute(
        select(RefreshToken.id).where(RefreshToken.token_hash == new_hash)
    )
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.id == stored.id)
        .values(revoked_at=now, replaced_by=new_result.scalar_one())
    )
    log.info("auth.refresh_ok", user_id=str(user.id))
    await session.commit()
    return pair


async def logout(session: AsyncSession, *, refresh_token: str) -> None:
    """Revoke the presented token. Idempotent — an unknown token is not an error."""
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_refresh_token(refresh_token),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(tz=UTC))
    )
    await session.commit()
