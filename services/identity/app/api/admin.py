"""Админ-панель: пользователи (ТЗ, раздел 2 «Администратор») и статистика DAU/MAU."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import Date, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_ADMIN, Principal
from testmatica_common.errors import ApiError
from testmatica_common.names import PersonName

from .. import sessions
from ..deps import auth, db, outbox
from ..models import ROLES, STATUS_ACTIVE, STATUS_BANNED, STATUS_DELETED, User, UserActivity, UserRole
from ..security import hash_password
from ..users import find_by_identifier, normalize, person_data
from .internal import _generate_password
from .me import check_timezone

router = APIRouter(prefix="/admin", tags=["admin"])
admin = auth.require(ROLE_ADMIN)

RESTORE_DAYS = 30  # решение №9: 30 дней на восстановление
DELETED_NAME = "Удалённый пользователь"


class AdminUser(BaseModel):
    id: UUID
    full_name: str
    last_name: str
    first_name: str
    middle_name: str
    email: str | None
    login: str | None
    phone: str | None
    roles: list[str]
    status: str
    status_reason: str | None
    two_factor_method: str | None
    managed_by_teacher_id: UUID | None
    email_verified: bool
    created_at: datetime
    last_seen_at: datetime | None
    deleted_at: datetime | None
    restore_until: datetime | None = Field(None, description="До какого момента удалённый аккаунт можно восстановить")
    timezone: str = "Europe/Moscow"

    @classmethod
    def of(cls, u: User) -> "AdminUser":
        return cls(
            id=u.id, full_name=u.full_name, last_name=u.last_name, first_name=u.first_name, middle_name=u.middle_name,
            email=u.email, login=u.login, phone=u.phone, roles=u.role_names, status=u.status,
            status_reason=u.status_reason, two_factor_method=u.two_factor_method, managed_by_teacher_id=u.managed_by_teacher_id,
            email_verified=u.email_verified_at is not None, created_at=u.created_at, last_seen_at=u.last_seen_at, timezone=u.timezone,
            deleted_at=u.deleted_at,
            restore_until=u.deleted_at + timedelta(days=RESTORE_DAYS) if u.deleted_at and not u.anonymized_at else None,
        )


class UsersPage(BaseModel):
    items: list[AdminUser]
    total: int


class UserEdit(BaseModel):
    name: PersonName | None = None
    email: EmailStr | None = None
    login: str | None = Field(None, min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    timezone: str | None = Field(None, min_length=1, max_length=64, description="Часовой пояс — по нему показывается расписание")

    _tz = field_validator("timezone")(check_timezone)


class RolesIn(BaseModel):
    roles: list[str] = Field(min_length=1)

    @field_validator("roles")
    @classmethod
    def _known(cls, v: list[str]) -> list[str]:
        if unknown := set(v) - set(ROLES):
            raise ValueError(f"Неизвестные роли: {', '.join(sorted(unknown))}")
        return sorted(set(v))


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class TempPassword(BaseModel):
    password: str


class DayPoint(BaseModel):
    day: date
    active: int
    registrations: int


class UserStats(BaseModel):
    total: int
    by_role: dict[str, int]
    by_status: dict[str, int]
    dau: int
    wau: int
    mau: int
    series: list[DayPoint]


async def _user(session: AsyncSession, user_id: UUID, lock: bool = False) -> User:
    u = await session.get(User, user_id, with_for_update=lock)
    if u is None:
        raise ApiError(404, "user_not_found", "Пользователь не найден")
    return u


def _not_self(principal: Principal, user_id: UUID) -> None:
    if principal.user_id == user_id:
        raise ApiError(409, "self_action", "С собственным аккаунтом так нельзя")


async def _changed(session: AsyncSession, u: User, principal: Principal, kind: str, extra: dict | None = None) -> None:
    """Реплики имён и ролей в других сервисах обновятся по identity.user.updated; отдельное событие — для аудита."""
    await outbox.event(session, "identity.user.updated", person_data(u), actor_id=principal.user_id)
    await outbox.event(session, f"identity.user.{kind}", {"user_id": str(u.id)} | (extra or {}), actor_id=principal.user_id)


@router.get("/users", response_model=UsersPage)
async def users(
    q: str | None = Query(None, max_length=100),
    role: str | None = Query(None, pattern="^(student|teacher|moderator|admin)$"),
    status: str | None = Query(None, pattern="^(active|pending_verification|banned|deleted)$"),
    ids: list[UUID] | None = Query(None, description="Конкретные пользователи — например, для имён в журнале аудита"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: Principal = Depends(admin),
    session: AsyncSession = Depends(db.session),
) -> UsersPage:
    query = select(User)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.where(or_(func.lower(User.full_name).like(like), User.email.like(like), User.login.like(like)))
    if role:
        query = query.where(User.roles.any(UserRole.role == role))
    if status:
        query = query.where(User.status == status)
    if ids:
        query = query.where(User.id.in_(ids[:200]))
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await session.execute(query.order_by(User.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return UsersPage(items=[AdminUser.of(u) for u in rows], total=total or 0)


@router.get("/users/{user_id}", response_model=AdminUser)
async def user(user_id: UUID, _: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> AdminUser:
    return AdminUser.of(await _user(session, user_id))


@router.patch("/users/{user_id}", response_model=AdminUser)
async def edit(user_id: UUID, body: UserEdit, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> AdminUser:
    u = await _user(session, user_id, lock=True)
    if u.anonymized_at:
        raise ApiError(409, "anonymized", "Аккаунт обезличен — изменить нельзя")
    changes = {}
    if body.name is not None and u.set_name(body.name):
        changes["full_name"] = u.full_name
    for field in ("email", "login"):
        value = getattr(body, field)
        if value is None or normalize(value) == getattr(u, field):
            continue
        other = await find_by_identifier(session, value)
        if other is not None and other.id != u.id:
            raise ApiError(409, f"{field}_taken", "Такой email уже занят" if field == "email" else "Такой логин уже занят")
        setattr(u, field, normalize(value))
        changes[field] = normalize(value)
    if body.timezone is not None and body.timezone != u.timezone:
        u.timezone = changes["timezone"] = body.timezone
    if changes:
        await _changed(session, u, principal, "edited_by_admin", {"fields": sorted(changes)})
        await session.commit()
    return AdminUser.of(u)


@router.put("/users/{user_id}/roles", response_model=AdminUser)
async def set_roles(user_id: UUID, body: RolesIn, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> AdminUser:
    """Ручная смена ролей. Снять роль администратора с себя нельзя — чтобы не остаться без админки."""
    u = await _user(session, user_id, lock=True)
    if principal.user_id == user_id and "admin" not in body.roles:
        raise ApiError(409, "self_action", "Нельзя снять роль администратора с себя")
    before = u.role_names
    if before == body.roles:
        return AdminUser.of(u)
    u.roles = [r for r in u.roles if r.role in body.roles] + [UserRole(role=r) for r in body.roles if r not in before]
    await session.flush()
    await session.refresh(u, ["roles"])
    # Новые роли попадут в токен при следующем продлении сессии (до 15 минут).
    await _changed(session, u, principal, "roles_changed", {"before": before, "after": body.roles})
    await session.commit()
    return AdminUser.of(u)


@router.post("/users/{user_id}/ban", response_model=AdminUser)
async def ban(user_id: UUID, body: ReasonIn, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> AdminUser:
    """Блокировка: все сессии завершаются, войти нельзя. Уже выданный access-токен доживает до 15 минут."""
    _not_self(principal, user_id)
    u = await _user(session, user_id, lock=True)
    if u.status == STATUS_DELETED:
        raise ApiError(409, "deleted", "Аккаунт удалён")
    u.status, u.status_reason = STATUS_BANNED, body.reason.strip()
    await sessions.revoke_all(session, u.id, "admin_ban")
    await outbox.event(session, "identity.user.banned", {"user_id": str(u.id), "reason": u.status_reason}, actor_id=principal.user_id)
    await session.commit()
    return AdminUser.of(u)


@router.post("/users/{user_id}/unban", response_model=AdminUser)
async def unban(user_id: UUID, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> AdminUser:
    u = await _user(session, user_id, lock=True)
    if u.status != STATUS_BANNED:
        raise ApiError(409, "not_banned", "Аккаунт не заблокирован")
    u.status, u.status_reason = STATUS_ACTIVE, None
    await outbox.event(session, "identity.user.unbanned", {"user_id": str(u.id)}, actor_id=principal.user_id)
    await session.commit()
    return AdminUser.of(u)


@router.post("/users/{user_id}/delete", response_model=AdminUser)
async def delete(user_id: UUID, body: ReasonIn, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> AdminUser:
    """Удаление: 30 дней можно восстановить, затем персональные данные обезличиваются (решение №9)."""
    _not_self(principal, user_id)
    u = await _user(session, user_id, lock=True)
    if u.status == STATUS_DELETED:
        return AdminUser.of(u)
    u.status, u.status_reason, u.deleted_at = STATUS_DELETED, body.reason.strip(), datetime.now(UTC)
    await sessions.revoke_all(session, u.id, "admin_delete")
    await outbox.event(session, "identity.user.deleted", {"user_id": str(u.id), "reason": u.status_reason}, actor_id=principal.user_id)
    await session.commit()
    return AdminUser.of(u)


@router.post("/users/{user_id}/restore", response_model=AdminUser)
async def restore(user_id: UUID, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> AdminUser:
    u = await _user(session, user_id, lock=True)
    if u.status != STATUS_DELETED:
        raise ApiError(409, "not_deleted", "Аккаунт не удалён")
    if u.anonymized_at:
        raise ApiError(409, "anonymized", "Прошло больше 30 дней — данные уже обезличены, восстановить нельзя")
    u.status, u.status_reason, u.deleted_at = STATUS_ACTIVE, None, None
    await outbox.event(session, "identity.user.restored", {"user_id": str(u.id)}, actor_id=principal.user_id)
    await session.commit()
    return AdminUser.of(u)


@router.post("/users/{user_id}/reset-password", response_model=TempPassword)
async def reset_password(user_id: UUID, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> TempPassword:
    """Временный пароль (показывается один раз) — администратор передаёт его пользователю; все сессии завершаются."""
    u = await _user(session, user_id, lock=True)
    if u.status in (STATUS_DELETED, STATUS_BANNED):
        raise ApiError(409, "inactive", "Сначала разблокируйте или восстановите аккаунт")
    password = _generate_password()
    u.password_hash = hash_password(password)
    await sessions.revoke_all(session, u.id, sessions.REASON_PASSWORD_RESET)
    await outbox.event(session, "identity.user.password_reset_by_admin", {"user_id": str(u.id)}, actor_id=principal.user_id)
    await session.commit()
    return TempPassword(password=password)


@router.get("/stats", response_model=UserStats)
async def stats(days: int = Query(30, ge=7, le=365), _: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> UserStats:
    """Пользователи по ролям и статусам, DAU/WAU/MAU и ряд по дням: активные и регистрации."""
    today = datetime.now(UTC).date()
    since = today - timedelta(days=days - 1)
    by_role = dict((await session.execute(
        select(UserRole.role, func.count()).join(User, User.id == UserRole.user_id).where(User.status != STATUS_DELETED).group_by(UserRole.role)
    )).all())
    by_status = dict((await session.execute(select(User.status, func.count()).group_by(User.status))).all())

    async def distinct_since(start: date) -> int:
        return await session.scalar(select(func.count(func.distinct(UserActivity.user_id))).where(UserActivity.day >= start)) or 0

    active = dict((await session.execute(
        select(UserActivity.day, func.count()).where(UserActivity.day >= since).group_by(UserActivity.day)
    )).all())
    reg_day = cast(func.timezone("UTC", User.created_at), Date)
    regs = dict((await session.execute(select(reg_day, func.count()).where(User.created_at >= since).group_by(reg_day))).all())
    series = [DayPoint(day=d, active=active.get(d, 0), registrations=regs.get(d, 0))
              for d in (since + timedelta(days=i) for i in range(days))]
    return UserStats(
        total=sum(v for k, v in by_status.items() if k != STATUS_DELETED), by_role=by_role, by_status=by_status,
        dau=await distinct_since(today), wau=await distinct_since(today - timedelta(days=6)),
        mau=await distinct_since(today - timedelta(days=29)), series=series,
    )


async def anonymize_deleted() -> None:
    """Фоновая задача: через 30 дней после удаления — обезличить (имя, email, телефон; логин — служебный)."""
    border = datetime.now(UTC) - timedelta(days=RESTORE_DAYS)
    async with db.sessionmaker() as session, session.begin():
        rows = (await session.execute(
            select(User).where(User.status == STATUS_DELETED, User.deleted_at < border, User.anonymized_at.is_(None))
            .with_for_update(skip_locked=True).limit(200)
        )).scalars().all()
        for u in rows:
            u.last_name, u.first_name, u.middle_name = "", "", ""
            u.full_name, u.email, u.phone = DELETED_NAME, None, None
            u.login = f"deleted-{u.id.hex[:12]}"
            u.password_hash = hash_password(_generate_password())
            u.anonymized_at = datetime.now(UTC)
            # Имя в репликах других сервисов станет «Удалённый пользователь» — отзывы и материалы остаются.
            await outbox.event(session, "identity.user.updated", person_data(u))
            await outbox.event(session, "identity.user.anonymized", {"user_id": str(u.id)})
