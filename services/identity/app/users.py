from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.ids import uuid7
from testmatica_common.names import PersonName

from .deps import outbox
from .models import User, UserRole


def normalize(identifier: str) -> str:
    return identifier.strip().lower()


async def find_by_identifier(session: AsyncSession, identifier: str) -> User | None:
    key = normalize(identifier)
    return (
        await session.execute(select(User).where(or_(User.email == key, User.login == key)))
    ).scalar_one_or_none()


async def find_by_email(session: AsyncSession, email: str) -> User | None:
    return (
        await session.execute(select(User).where(User.email == normalize(email)))
    ).scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    *,
    email: str | None,
    password_hash: str,
    name: PersonName,
    roles: list[str],
    status: str,
    actor_id: UUID | None = None,
    **fields,
) -> User:
    user = User(
        id=uuid7(),
        email=normalize(email) if email else None,
        password_hash=password_hash,
        status=status,
        roles=[UserRole(role=r) for r in roles],
        **fields,
    )
    user.set_name(name)
    session.add(user)
    await session.flush()
    await outbox.event(
        session,
        "identity.user.registered",
        person_data(user) | {"status": status},
        actor_id=actor_id or user.id,
    )
    return user


def person_data(user: User) -> dict:
    """Публичные данные пользователя для реплик в других сервисах (имена в списках)."""
    return {
        "user_id": str(user.id),
        "full_name": user.full_name,
        "last_name": user.last_name,
        "first_name": user.first_name,
        "middle_name": user.middle_name,
        "login": user.login,
        "roles": user.role_names,
        "avatar_file_id": str(user.avatar_file_id) if user.avatar_file_id else None,
    }
