"""Сессии пользователя: выдача access-токена и ротация refresh-токена в httpOnly-cookie."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Request, Response
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError
from testmatica_common.ids import uuid7

from .config import settings
from .deps import issuer, outbox
from .models import STATUS_ACTIVE, RefreshToken, User, UserActivity
from .schemas import Authenticated, UserOut
from .security import generate_refresh_token, hash_token

# Два запроса /refresh почти одновременно (например, две вкладки) не должны
# восприниматься как кража токена.
REUSE_GRACE = timedelta(seconds=10)

REASON_ROTATED = "rotated"
REASON_LOGOUT = "logout"
REASON_PASSWORD_RESET = "password_reset"
REASON_REUSE = "reuse"
REASON_TEACHER = "teacher_logout"  # педагог вывел ученика из аккаунта (оставил вход на школьном компьютере)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.refresh_cookie_name,
        token,
        max_age=settings.refresh_token_ttl_days * 86400,
        path=settings.refresh_cookie_path,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
    )


def clear_cookie(response: Response) -> None:
    response.delete_cookie(settings.refresh_cookie_name, path=settings.refresh_cookie_path)


def _authenticated(user: User) -> Authenticated:
    return Authenticated(
        access_token=issuer.access_token(user),
        expires_in=settings.access_token_ttl_seconds,
        user=UserOut.of(user),
    )


def _new_refresh(user: User, family_id: UUID, request: Request) -> tuple[RefreshToken, str]:
    raw = generate_refresh_token()
    row = RefreshToken(
        user_id=user.id,
        family_id=family_id,
        token_hash=hash_token(raw),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
        user_agent=(request.headers.get("user-agent") or "")[:300],
        ip=client_ip(request),
    )
    return row, raw


async def start_session(
    session: AsyncSession, user: User, request: Request, response: Response
) -> Authenticated:
    row, raw = _new_refresh(user, uuid7(), request)
    session.add(row)
    user.last_seen_at = datetime.now(UTC)
    await mark_active(session, user)
    await outbox.event(
        session, "identity.user.logged_in", {"user_id": str(user.id), "ip": client_ip(request)}, actor_id=user.id
    )
    _set_cookie(response, raw)
    return _authenticated(user)


async def rotate(session: AsyncSession, request: Request, response: Response) -> Authenticated:
    raw = request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        raise ApiError(401, "no_session", "Сессия не найдена, войдите снова")
    now = datetime.now(UTC)
    current = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)).with_for_update()
        )
    ).scalar_one_or_none()
    if current is None or current.expires_at <= now:
        raise ApiError(401, "session_expired", "Сессия истекла, войдите снова")

    user = await session.get(User, current.user_id)
    if user is None or user.status != STATUS_ACTIVE:
        raise ApiError(401, "session_expired", "Сессия истекла, войдите снова")

    if current.revoked_at is not None:
        if current.revoke_reason == REASON_ROTATED and now - current.revoked_at <= REUSE_GRACE:
            # Параллельный запрос: новый refresh уже выдан, отдаём только access-токен.
            return _authenticated(user)
        # Старый токен использован повторно — вероятно, его украли. Закрываем всю цепочку.
        await revoke_family(session, current.family_id, REASON_REUSE)
        await outbox.event(
            session,
            "identity.session.token_reuse_detected",
            {"user_id": str(user.id), "ip": client_ip(request)},
            actor_id=user.id,
        )
        await session.commit()
        raise ApiError(401, "session_revoked", "Сессия завершена в целях безопасности, войдите снова")

    current.revoked_at = now
    current.revoke_reason = REASON_ROTATED
    row, new_raw = _new_refresh(user, current.family_id, request)
    session.add(row)
    user.last_seen_at = now
    await mark_active(session, user)
    _set_cookie(response, new_raw)
    return _authenticated(user)


async def mark_active(session: AsyncSession, user: User) -> None:
    """Отметить день активности (DAU/MAU): сессия продлевается примерно раз в 15 минут, пока человек на сайте."""
    await session.execute(
        pg_insert(UserActivity).values(user_id=user.id, day=datetime.now(UTC).date()).on_conflict_do_nothing()
    )


async def revoke_by_cookie(session: AsyncSession, request: Request) -> None:
    raw = request.cookies.get(settings.refresh_cookie_name)
    if not raw:
        return
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw), RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoke_reason=REASON_LOGOUT)
    )


async def revoke_family(session: AsyncSession, family_id: UUID, reason: str) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoke_reason=reason)
    )


async def revoke_all(session: AsyncSession, user_id: UUID, reason: str) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoke_reason=reason)
    )
