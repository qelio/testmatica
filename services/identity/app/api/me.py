"""Личный кабинет: свои данные, аватар, email, пароль, двухфакторная защита."""

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal
from testmatica_common.errors import ApiError
from testmatica_common.names import PersonName

from .. import avatars, legal_consents, otp, sessions
from ..config import settings
from ..deps import auth, db, media, outbox
from ..models import STATUS_ACTIVE, User
from ..schemas import ConsentsIn, UserOut, _check_password
from ..security import hash_password, mask_email, verify_password
from ..users import find_by_identifier, normalize, person_data

router = APIRouter(prefix="/me", tags=["me"])

STAFF = {"moderator", "admin"}  # им 2FA обязательна без исключений (решение №6)


def check_timezone(v: str | None) -> str | None:
    """Часовой пояс из базы IANA (Europe/Moscow, Asia/Yekaterinburg…)."""
    if v is None:
        return v
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Неизвестный часовой пояс") from None
    return v


class ProfileIn(BaseModel):
    name: PersonName | None = Field(None, description="Фамилия, имя, отчество")
    timezone: str | None = Field(None, min_length=1, max_length=64)

    _tz = field_validator("timezone")(check_timezone)


class AvatarIn(BaseModel):
    file_id: UUID | None = Field(description="null — убрать фото")


class EmailIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class CodeIn(BaseModel):
    challenge_id: UUID
    code: str = Field(min_length=4, max_length=10)


class EmailChallenge(BaseModel):
    challenge_id: UUID
    destination: str


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    _password = field_validator("new_password")(_check_password)


class TwoFactorIn(BaseModel):
    enabled: bool
    password: str = Field(min_length=1, max_length=128)


async def _load(session: AsyncSession, principal: Principal, lock: bool = False) -> User:
    user = await session.get(User, principal.user_id, with_for_update=lock)
    if user is None or user.status != STATUS_ACTIVE:
        raise ApiError(401, "invalid_token", "Пользователь не найден или заблокирован")
    return user


async def _out(session: AsyncSession, user: User) -> UserOut:
    url = None
    if user.avatar_file_id:
        try:
            found = await media.post("/internal/files/urls", json={"file_ids": [str(user.avatar_file_id)]})
            url = (found.get(str(user.avatar_file_id)) or {}).get("url")
        except ApiError:
            url = None  # media недоступен — страница откроется без фото
    return UserOut.of(user, avatar_url=url, consent_required=await legal_consents.required(session, user.id))


def _check_password_or_fail(user: User, password: str) -> None:
    if not verify_password(user.password_hash, password):
        raise ApiError(403, "wrong_password", "Неверный пароль")


@router.get("", response_model=UserOut)
async def me(principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> UserOut:
    return await _out(session, await _load(session, principal))


@router.patch("", response_model=UserOut)
async def update_me(body: ProfileIn, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> UserOut:
    """Имя и часовой пояс. Имя в других сервисах обновится по событию."""
    user = await _load(session, principal, lock=True)
    changed = False
    if body.name is not None and user.set_name(body.name):
        changed = True
    if body.timezone is not None and body.timezone != user.timezone:
        user.timezone, changed = body.timezone, True
    if changed:
        await outbox.event(session, "identity.user.updated", person_data(user), actor_id=user.id)
        await session.commit()
    return await _out(session, user)


@router.put("/avatar", response_model=UserOut)
async def set_avatar(body: AvatarIn, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> UserOut:
    """Фото профиля: сначала загрузить файл в media (purpose avatar), потом передать его id сюда.
    Это же фото — в анкете репетитора (marketplace получает его событием)."""
    user = await _load(session, principal, lock=True)
    await avatars.set_avatar(session, user, body.file_id)
    await session.commit()
    return await _out(session, user)


@router.post("/email", response_model=EmailChallenge)
async def change_email(body: EmailIn, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> EmailChallenge:
    """Сменить или добавить email: пароль, затем код на новый адрес."""
    if not settings.email_codes:
        raise ApiError(503, "email_unavailable", "Смена email скоро появится — для неё нужны письма с кодом")
    user = await _load(session, principal)
    _check_password_or_fail(user, body.password)
    email = normalize(body.email)
    # Тот же адрес — только чтобы подтвердить его (регистрировались, пока почты не было, решение №29).
    if email == user.email and user.email_verified_at is not None:
        raise ApiError(409, "same_email", "Это ваш текущий email")
    other = await find_by_identifier(session, email)
    if other is not None and other.id != user.id:
        raise ApiError(409, "email_taken", "Этот email уже занят")
    challenge = await otp.issue(session, user, otp.PURPOSE_EMAIL_CHANGE, destination=email)
    await session.commit()
    return EmailChallenge(challenge_id=challenge.id, destination=mask_email(email))


@router.post("/email/confirm", response_model=UserOut)
async def confirm_email(body: CodeIn, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> UserOut:
    challenge = await otp.verify(session, body.challenge_id, body.code, otp.PURPOSE_EMAIL_CHANGE)
    if challenge.user_id != principal.user_id:
        raise ApiError(400, "invalid_code", "Код недействителен или истёк. Запросите новый.")
    user = await _load(session, principal, lock=True)
    other = await find_by_identifier(session, challenge.destination)
    if other is not None and other.id != user.id:
        raise ApiError(409, "email_taken", "Этот email уже занят")
    first_contact = user.email is None
    user.email, user.email_verified_at = challenge.destination, datetime.now(UTC)
    # Решение №6: ученик, созданный педагогом, привязал контакт — включаем вход с кодом.
    if first_contact and user.two_factor_method is None:
        user.two_factor_method = "email"
    await outbox.event(session, "identity.user.email_changed", {"user_id": str(user.id)}, actor_id=user.id)
    await session.commit()
    return await _out(session, user)


@router.post("/password", status_code=204)
async def change_password(
    body: PasswordIn, request: Request, response: Response,
    principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session),
) -> None:
    """Смена пароля: остальные устройства выходят из аккаунта, текущее получает новую сессию."""
    user = await _load(session, principal, lock=True)
    _check_password_or_fail(user, body.current_password)
    user.password_hash = hash_password(body.new_password)
    await sessions.revoke_all(session, user.id, sessions.REASON_PASSWORD_RESET)
    await sessions.start_session(session, user, request, response)
    await outbox.event(session, "identity.user.password_changed", {"user_id": str(user.id)}, actor_id=user.id)
    await session.commit()


@router.put("/2fa", response_model=UserOut)
async def set_two_factor(body: TwoFactorIn, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> UserOut:
    """Вход с кодом на email: включить (нужен подтверждённый email) или выключить (кроме модераторов и администраторов)."""
    user = await _load(session, principal, lock=True)
    _check_password_or_fail(user, body.password)
    if body.enabled:
        if not settings.email_codes:
            raise ApiError(503, "email_unavailable", "Вход с кодом из письма скоро появится")
        if not user.email or user.email_verified_at is None:
            raise ApiError(409, "email_required", "Сначала добавьте и подтвердите email — на него будут приходить коды")
        user.two_factor_method = "email"
    else:
        if STAFF & set(user.role_names):
            raise ApiError(409, "two_factor_required", "Модераторам и администраторам вход с кодом обязателен")
        user.two_factor_method = None
    await outbox.event(session, "identity.user.two_factor_changed", {"user_id": str(user.id), "enabled": body.enabled}, actor_id=user.id)
    await session.commit()
    return await _out(session, user)


@router.post("/consents", response_model=UserOut)
async def give_consents(body: ConsentsIn, request: Request, principal: Principal = Depends(auth.principal),
                        session: AsyncSession = Depends(db.session)) -> UserOut:
    """Окно согласия при входе: соглашение и обработка ПД (текущие редакции). Для ученика младше 14 лет — родитель."""
    user = await _load(session, principal)
    if await legal_consents.required(session, user.id):
        await legal_consents.record(session, user.id, request, source="first_login", by_representative=body.by_representative)
        await session.commit()
    return await _out(session, user)
