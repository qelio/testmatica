"""Одноразовые коды. Сам код не хранится — только его HMAC.
Письмо с кодом отправляет сервис notification по команде через outbox."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError

from .config import settings
from .deps import outbox
from .models import OtpChallenge, User
from .security import codes_equal, generate_code, hash_code

PURPOSE_EMAIL_VERIFICATION = "email_verification"
PURPOSE_LOGIN = "login"
PURPOSE_PASSWORD_RESET = "password_reset"


def _now() -> datetime:
    return datetime.now(UTC)


async def issue(session: AsyncSession, user: User, purpose: str) -> OtpChallenge:
    """Создать новый код. Предыдущие неиспользованные коды того же назначения гасятся."""
    assert user.email, "коды отправляются только на email"
    now = _now()
    await session.execute(
        update(OtpChallenge)
        .where(
            OtpChallenge.user_id == user.id,
            OtpChallenge.purpose == purpose,
            OtpChallenge.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    code = generate_code()
    challenge = OtpChallenge(
        user_id=user.id,
        purpose=purpose,
        code_hash=hash_code(code),
        destination=user.email,
        expires_at=now + timedelta(seconds=settings.otp_ttl_seconds),
        last_sent_at=now,
        attempts=0,
    )
    session.add(challenge)
    await session.flush()
    await _send(session, user, challenge, code)
    return challenge


async def resend(session: AsyncSession, challenge_id: UUID) -> None:
    """Выслать код повторно. Для несуществующего кода молча ничего не делает,
    чтобы по ответу нельзя было понять, есть ли такой аккаунт."""
    challenge = await session.get(OtpChallenge, challenge_id, with_for_update=True)
    if challenge is None or challenge.consumed_at is not None:
        return
    now = _now()
    wait = settings.otp_resend_interval_seconds - (now - challenge.last_sent_at).total_seconds()
    if wait > 0:
        raise ApiError(
            429, "resend_too_early", "Код можно запросить повторно чуть позже", {"retry_after": int(wait) + 1}
        )
    user = await session.get(User, challenge.user_id)
    assert user is not None
    code = generate_code()
    challenge.code_hash = hash_code(code)
    challenge.attempts = 0
    challenge.expires_at = now + timedelta(seconds=settings.otp_ttl_seconds)
    challenge.last_sent_at = now
    await _send(session, user, challenge, code)


async def verify(session: AsyncSession, challenge_id: UUID, code: str, purpose: str) -> OtpChallenge:
    """Проверить код. При неверном коде счётчик попыток сохраняется (commit) до выброса ошибки,
    поэтому вызывать до любых других изменений в сессии."""
    challenge = await session.get(OtpChallenge, challenge_id, with_for_update=True)
    if (
        challenge is None
        or challenge.purpose != purpose
        or challenge.consumed_at is not None
        or challenge.expires_at <= _now()
    ):
        raise ApiError(400, "invalid_code", "Код недействителен или истёк. Запросите новый.")
    if challenge.attempts >= settings.otp_max_attempts:
        raise ApiError(400, "too_many_attempts", "Слишком много неверных попыток. Запросите новый код.")
    if not codes_equal(challenge.code_hash, code):
        challenge.attempts += 1
        attempts_left = settings.otp_max_attempts - challenge.attempts
        await session.commit()
        raise ApiError(400, "invalid_code", "Неверный код", {"attempts_left": attempts_left})
    challenge.consumed_at = _now()
    return challenge


async def _send(session: AsyncSession, user: User, challenge: OtpChallenge, code: str) -> None:
    await outbox.command(
        session,
        queue="notification.email",
        type="notification.email.send",
        data={
            "to": challenge.destination,
            "template": challenge.purpose,
            "params": {
                "name": user.full_name,
                "code": code,
                "ttl_minutes": settings.otp_ttl_seconds // 60,
            },
        },
        actor_id=user.id,
    )
