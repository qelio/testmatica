"""Реплика пользователей: имена авторов и учеников на досках."""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .models import Person

UNKNOWN_NAME = "Пользователь"


async def upsert(session: AsyncSession, data: dict) -> None:
    values = {"user_id": UUID(data["user_id"]), "full_name": data["full_name"], "login": data.get("login")}
    update = {"full_name": values["full_name"], "login": values["login"]}
    if data.get("roles") is not None:
        values["roles"] = update["roles"] = data["roles"]
    await session.execute(insert(Person).values(**values).on_conflict_do_update(index_elements=["user_id"], set_=update))


async def names(session: AsyncSession, user_ids: Iterable[UUID]) -> dict[UUID, str]:
    ids = {i for i in user_ids if i is not None}
    if not ids:
        return {}
    rows = await session.execute(select(Person.user_id, Person.full_name).where(Person.user_id.in_(ids)))
    return dict(rows.all())


async def on_identity_event(envelope: Envelope, session: AsyncSession) -> None:
    if envelope.type in ("identity.user.registered", "identity.user.snapshot", "identity.user.updated"):
        await upsert(session, envelope.data)


async def name_of(session: AsyncSession, user_id: UUID) -> str:
    return (await names(session, [user_id])).get(user_id, UNKNOWN_NAME)
