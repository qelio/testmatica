"""Реплика имён пользователей (события identity)."""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .models import Person

UNKNOWN_NAME = "Участник"


async def on_identity_event(envelope: Envelope, session: AsyncSession) -> None:
    if envelope.type in ("identity.user.registered", "identity.user.snapshot", "identity.user.updated"):
        d = envelope.data
        await session.execute(
            insert(Person).values(user_id=UUID(d["user_id"]), full_name=d["full_name"])
            .on_conflict_do_update(index_elements=["user_id"], set_={"full_name": d["full_name"]})
        )


async def names(session: AsyncSession, user_ids: Iterable[UUID]) -> dict[UUID, str]:
    ids = {i for i in user_ids if i}
    if not ids:
        return {}
    return dict((await session.execute(select(Person.user_id, Person.full_name).where(Person.user_id.in_(ids)))).all())
