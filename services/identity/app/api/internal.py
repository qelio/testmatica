"""Внутренние эндпоинты для других сервисов (classroom и др.). Наружу не публикуются."""

import re
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError
from testmatica_common.internal import internal_guard
from testmatica_common.names import PersonName

from .. import avatars, sessions
from ..config import settings
from ..deps import db, outbox
from ..models import STATUS_ACTIVE, User
from ..security import hash_password
from ..users import create_user, find_by_identifier, normalize, person_data

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(internal_guard(settings.internal_token))])

LOGIN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")

_TRANSLIT = dict(
    zip(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
        "a b v g d e e zh z i y k l m n o p r s t u f h ts ch sh sch - y - e yu ya".split(),
    )
)


class PersonOut(BaseModel):
    id: UUID
    full_name: str
    first_name: str = ""
    login: str | None
    roles: list[str]
    managed_by_teacher_id: UUID | None

    @classmethod
    def of(cls, user: User) -> "PersonOut":
        return cls(
            id=user.id,
            full_name=user.full_name,
            first_name=user.first_name,
            login=user.login,
            roles=user.role_names,
            managed_by_teacher_id=user.managed_by_teacher_id,
        )


class ManagedStudentCreate(PersonName):
    teacher_id: UUID
    login: str | None = None
    password: str | None = Field(None, min_length=6, max_length=128)

    @field_validator("login")
    @classmethod
    def _login(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = normalize(value)
        if not LOGIN_RE.match(value):
            raise ValueError("Логин: 3–32 символа, латинские буквы, цифры, точка, дефис, подчёркивание")
        return value


class ManagedStudentUpdate(BaseModel):
    teacher_id: UUID
    name: PersonName | None = None
    reset_password: bool = False


class Credentials(BaseModel):
    user: PersonOut
    login: str | None
    password: str | None


def _generate_login(first_name: str) -> str:
    """Логин из имени (не фамилии) транслитом: «Оля» → olya4821."""
    base = "".join(_TRANSLIT.get(ch, ch) for ch in first_name.lower().split()[0] if ch.isalnum() or ch in _TRANSLIT)
    base = re.sub(r"[^a-z0-9]", "", base.replace("-", ""))[:20] or "student"
    return f"{base}{secrets.randbelow(9000) + 1000}"


def _generate_password() -> str:
    # Без похожих символов (0/O, 1/l), чтобы педагог мог продиктовать пароль ребёнку.
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8)) + str(secrets.randbelow(10))


@router.get("/users/lookup", response_model=PersonOut)
async def lookup(identifier: str = Query(min_length=1), session: AsyncSession = Depends(db.session)) -> PersonOut:
    user = await find_by_identifier(session, identifier)
    if user is None or user.status != STATUS_ACTIVE:
        raise ApiError(404, "user_not_found", "Пользователь с таким логином или email не найден")
    return PersonOut.of(user)


@router.post("/managed-students", response_model=Credentials, status_code=201)
async def create_managed_student(
    body: ManagedStudentCreate, session: AsyncSession = Depends(db.session)
) -> Credentials:
    """Педагог создаёт аккаунт ученика: имя, логин и пароль (авто или вручную), email не нужен."""
    password = body.password or _generate_password()
    login = body.login or _generate_login(body.first_name)
    if body.login and await find_by_identifier(session, login):
        raise ApiError(409, "login_taken", "Такой логин уже занят")
    for attempt in range(5):
        try:
            async with session.begin_nested():
                user = await create_user(
                    session,
                    email=None,
                    password_hash=hash_password(password),
                    name=body,
                    roles=["student"],
                    status=STATUS_ACTIVE,
                    actor_id=body.teacher_id,
                    login=login,
                    managed_by_teacher_id=body.teacher_id,
                )
            break
        except IntegrityError:
            if body.login or attempt == 4:
                raise ApiError(409, "login_taken", "Такой логин уже занят") from None
            login = _generate_login(body.first_name)
    await session.commit()
    return Credentials(user=PersonOut.of(user), login=login, password=password)


@router.patch("/managed-students/{user_id}", response_model=Credentials)
async def update_managed_student(
    user_id: UUID, body: ManagedStudentUpdate, session: AsyncSession = Depends(db.session)
) -> Credentials:
    user = await session.get(User, user_id)
    if user is None or user.managed_by_teacher_id != body.teacher_id:
        raise ApiError(404, "user_not_found", "Ученик не найден или управляется другим педагогом")
    password = None
    if body.name:
        user.set_name(body.name)
    if body.reset_password:
        password = _generate_password()
        user.password_hash = hash_password(password)
        await sessions.revoke_all(session, user.id, sessions.REASON_PASSWORD_RESET)
    await outbox.event(
        session,
        "identity.user.updated",
        person_data(user) | {"password_reset": body.reset_password},
        actor_id=body.teacher_id,
    )
    await session.commit()
    return Credentials(user=PersonOut.of(user), login=user.login, password=password)


class PresenceIn(BaseModel):
    user_ids: list[UUID] = Field(max_length=200)


@router.post("/users/presence", response_model=dict[str, str | None])
async def presence(body: PresenceIn, session: AsyncSession = Depends(db.session)) -> dict[str, str | None]:
    """Когда пользователь был в сети (вход или продление сессии — примерно раз в 15 минут, пока он активен).
    Для онлайн-статуса в профиле репетитора."""
    if not body.user_ids:
        return {}
    rows = await session.execute(select(User.id, User.last_seen_at).where(User.id.in_(body.user_ids)))
    return {str(uid): seen.isoformat() if seen else None for uid, seen in rows}


class AvatarIn(BaseModel):
    file_id: UUID | None


@router.post("/users/{user_id}/avatar", status_code=204)
async def set_avatar(user_id: UUID, body: AvatarIn, session: AsyncSession = Depends(db.session)) -> None:
    """Фото профиля из анкеты репетитора (marketplace): оно же — фото в кабинете."""
    user = await session.get(User, user_id, with_for_update=True)
    if user is None or user.status != STATUS_ACTIVE:
        raise ApiError(404, "user_not_found", "Пользователь не найден")
    await avatars.set_avatar(session, user, body.file_id)
    await session.commit()
