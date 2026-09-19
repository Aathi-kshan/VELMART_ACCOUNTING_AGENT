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
from app.services.audit_service import write_audit_log

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
    #: Computed once, here, while RLS is still armed for this transaction.
    #: The router must reuse this rather than calling store_ids_for again —
    #: login()/refresh() commit before returning, and set_config(..., true)
    #: is transaction-scoped, so a second query after that commit would run
    #: with no RLS context at all (this was a real, RLS-invisible-until-now
    #: bug: it silently returned zero rows under the superuser test
    #: connection, and raises under app_user's real enforcement).
    store_ids: list[uuid.UUID]


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
        store_ids=store_ids,
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
    #
    # This can't be a plain SELECT: `users` carries RLS (migration 0006) and
    # app_user has no context to scope it by yet — that's exactly what this
    # query is trying to discover. auth_find_user_by_email (migration 0010)
    # is a SECURITY DEFINER function, the one sanctioned bypass for this exact
    # lookup.
    result = await session.execute(
        select(User).from_statement(text("SELECT * FROM auth_find_user_by_email(:email)")),
        {"email": email},
    )
    users = result.scalars().all()
    user = users[0] if len(users) == 1 else None

    if user is None:
        # No company to attribute an audit row to, so this is logged only.
        log.warning("auth.login_unknown_email", ip_address=ip_address)
        raise AuthenticationError("Invalid email or password.")

    # The company is known now — arm RLS for the rest of this transaction so
    # every query below (the lockout/failure update, the audit row, issuing
    # tokens and reading store_ids_for) is a normal, RLS-scoped query rather
    # than a further special case.
    await set_rls_context(session, company_id=user.company_id, role=str(user.role))

    now = datetime.now(tz=UTC)

    if user.locked_until is not None and user.locked_until > now:
        await write_audit_log(
            session,
            company_id=user.company_id,
            action="LOGIN_FAILED",
            entity_type="user",
            entity_id=user.id,
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
        await write_audit_log(
            session,
            company_id=user.company_id,
            action="LOGIN_FAILED",
            entity_type="user",
            entity_id=user.id,
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
    await write_audit_log(
        session,
        company_id=user.company_id,
        action="LOGIN",
        entity_type="user",
        entity_id=user.id,
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

    # refresh_tokens carries no company_id and no RLS (migration 0006), so
    # the lookup above needed no context. `users` does, though, and the
    # company isn't known until this row resolves it — auth_find_user_by_id
    # (migration 0010) is the same sanctioned bypass login() uses. RLS is
    # armed from its result before anything else here touches a tenant table
    # (store_ids_for, a few lines below, queries `stores`).
    user_result = await session.execute(
        select(User).from_statement(text("SELECT * FROM auth_find_user_by_id(:user_id)")),
        {"user_id": str(stored.user_id)},
    )
    user = user_result.scalar_one_or_none()
    if user is not None:
        await set_rls_context(session, company_id=user.company_id, role=str(user.role))

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
        if user is not None:
            await write_audit_log(
                session,
                company_id=user.company_id,
                action="LOGIN_FAILED",
                entity_type="user",
                entity_id=user.id,
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

    if user is None or not user.is_active:
        raise RefreshTokenError("Invalid refresh token.")

    # Claim the token before minting anything. Reading `revoked_at` above and
    # revoking it at the end would be check-then-act: two requests presenting
    # the same token both see it live, both mint a pair, and one token yields
    # two live families — and because each marks the row revoked itself,
    # neither is ever seen as a replay, so the reuse detection above never
    # fires for a genuinely stolen token.
    #
    # This UPDATE decides the winner in the database. It takes the row lock,
    # so a concurrent request blocks here and then finds `revoked_at` already
    # set, matches no row, and gets nothing back. If this request fails later
    # the whole transaction rolls back, releasing the claim.
    claimed = await session.scalar(
        update(RefreshToken)
        .where(RefreshToken.id == stored.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
        .returning(RefreshToken.id)
    )
    if claimed is None:
        # Another request rotated this token while we were validating it. We
        # cannot tell a client retrying after a network flake from an
        # attacker racing the real user, so this fails closed without
        # revoking the family: whichever caller lost simply has no valid
        # token. A later replay of this same value still lands on the
        # reuse-detection path above, which is where a stolen token is
        # supposed to be caught.
        log.warning("auth.refresh_lost_race", user_id=str(stored.user_id))
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
        .values(replaced_by=new_result.scalar_one())
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
