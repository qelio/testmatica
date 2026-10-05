"""Личные ключи доступа: выпустить, посмотреть, отозвать (решение №41)."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal
from testmatica_common.errors import ApiError

from .. import api_keys
from ..deps import auth, db, outbox
from ..models import STATUS_ACTIVE, ApiKey, User

router = APIRouter(prefix="/me/api-keys", tags=["api-keys"])


class ApiKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=80, description="Для чего ключ, например «Claude Desktop»")

    @field_validator("name")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Назовите ключ")
        return v


class ApiKeyOut(BaseModel):
    id: UUID
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    key: str = Field(description="Сам ключ — показывается один раз")


def _out(k: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(id=k.id, name=k.name, prefix=k.prefix, created_at=k.created_at, last_used_at=k.last_used_at)


async def _user(session: AsyncSession, principal: Principal) -> User:
    user = await session.get(User, principal.user_id)
    if user is None or user.status != STATUS_ACTIVE:
        raise ApiError(401, "invalid_token", "Пользователь не найден или заблокирован")
    if not api_keys.ALLOWED_ROLES & set(user.role_names):
        raise ApiError(403, "forbidden", "Ключи доступа выпускают педагоги")
    return user


@router.get("", response_model=list[ApiKeyOut])
async def list_keys(principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> list[ApiKeyOut]:
    rows = await session.execute(
        select(ApiKey).where(ApiKey.user_id == principal.user_id, ApiKey.revoked_at.is_(None)).order_by(ApiKey.created_at.desc())
    )
    return [_out(k) for k in rows.scalars()]


@router.post("", response_model=ApiKeyCreated, status_code=201)
async def create_key(body: ApiKeyIn, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> ApiKeyCreated:
    """Выпустить ключ. Сам ключ показывается один раз — дальше видно только начало «tm_ab12…»."""
    user = await _user(session, principal)
    active = await session.scalar(
        select(func.count()).select_from(ApiKey).where(ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None))
    )
    if active >= api_keys.MAX_KEYS:
        raise ApiError(409, "too_many_keys", f"Не больше {api_keys.MAX_KEYS} ключей — отзовите ненужные")
    raw = api_keys.generate()
    key = ApiKey(user_id=user.id, name=body.name, prefix=raw[:11], key_hash=api_keys.digest(raw))
    session.add(key)
    await session.flush()
    await outbox.event(session, "identity.api_key.created", {"user_id": str(user.id), "key_id": str(key.id), "name": key.name},
                       actor_id=user.id)
    await session.commit()
    await session.refresh(key)
    return ApiKeyCreated(**_out(key).model_dump(), key=raw)


@router.delete("/{key_id}", status_code=204)
async def revoke_key(key_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> None:
    key = await session.get(ApiKey, key_id, with_for_update=True)
    if key is None or key.user_id != principal.user_id or key.revoked_at:
        raise ApiError(404, "key_not_found", "Ключ не найден")
    key.revoked_at = datetime.now(UTC)
    await outbox.event(session, "identity.api_key.revoked", {"user_id": str(key.user_id), "key_id": str(key.id), "name": key.name},
                       actor_id=principal.user_id)
    await session.commit()
