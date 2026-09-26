"""Переименование предмета в справочнике (content.subject.updated): обновить сохранённые названия."""

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .deps import subjects
from .models import Group


async def on_subject_updated(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    subjects.reset()
    if d["old_name"] != d["name"]:
        await session.execute(update(Group).where(Group.subject == d["old_name"]).values(subject=d["name"]))
