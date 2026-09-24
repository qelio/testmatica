"""Реплика пользователей: имена для списков."""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .models import Person

UNKNOWN_NAME = "Пользователь"


async def upsert(
    session: AsyncSession, user_id: UUID, full_name: str, login: str | None, roles: list[str] | None = None
) -> None:
    values = {"user_id": user_id, "full_name": full_name, "login": login}
    update = {"full_name": full_name, "login": login}
    if roles is not None:
        values["roles"] = roles
        update["roles"] = roles
    await session.execute(
        insert(Person).values(**values).on_conflict_do_update(index_elements=["user_id"], set_=update)
    )


async def upsert_from_identity(session: AsyncSession, data: dict) -> None:
    """Данные в формате PersonOut из identity (внутренний API)."""
    await upsert(session, UUID(str(data["id"])), data["full_name"], data.get("login"), data.get("roles"))


async def names(session: AsyncSession, user_ids: Iterable[UUID]) -> dict[UUID, Person]:
    ids = set(user_ids)
    if not ids:
        return {}
    rows = await session.execute(select(Person).where(Person.user_id.in_(ids)))
    return {p.user_id: p for p in rows.scalars()}


async def name_of(session: AsyncSession, user_id: UUID) -> str:
    person = await session.get(Person, user_id)
    return person.full_name if person else UNKNOWN_NAME


async def on_identity_event(envelope: Envelope, session: AsyncSession) -> None:
    if envelope.type not in ("identity.user.registered", "identity.user.snapshot", "identity.user.updated"):
        return
    data = envelope.data
    await upsert(session, UUID(data["user_id"]), data["full_name"], data.get("login"), data.get("roles"))
