"""Переименование предмета в справочнике (content.subject.updated): обновить сохранённые названия."""

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .models import Attendance, Grade, Plan, PlanTemplate


async def on_subject_updated(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    if d["old_name"] == d["name"]:
        return
    for model in (Grade, Attendance, Plan, PlanTemplate):
        await session.execute(update(model).where(model.subject == d["old_name"]).values(subject=d["name"]))
