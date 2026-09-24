from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.ids import uuid7

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
    full_name: str,
    roles: list[str],
    status: str,
    actor_id: UUID | None = None,
    **fields,
) -> User:
    user = User(
        id=uuid7(),
        email=normalize(email) if email else None,
        password_hash=password_hash,
        full_name=full_name,
        status=status,
        teacher_mode="school" if "teacher" in roles else None,
        roles=[UserRole(role=r) for r in roles],
        **fields,
    )
    session.add(user)
    await session.flush()
    await outbox.event(
        session,
        "identity.user.registered",
        {"user_id": str(user.id), "roles": sorted(roles), "status": status},
        actor_id=actor_id or user.id,
    )
    return user
