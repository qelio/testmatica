"""Переименование предмета в справочнике (content.subject.updated): обновить сохранённые названия."""

from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .models import Assignment, Exam, Task, Test, Topic


async def on_subject_updated(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    sid = UUID(d["subject_id"])
    await session.execute(update(Task).where(Task.subject_id == sid).values(subject_name=d["name"]))
    await session.execute(update(Topic).where(Topic.subject_id == sid).values(subject_name=d["name"]))
    await session.execute(update(Exam).where(Exam.subject_id == sid).values(subject_name=d["name"]))
    await session.execute(update(Test).where(Test.subject_id == sid).values(subject_name=d["name"]))
    await session.execute(update(Assignment).where(Assignment.subject_id == sid).values(subject_name=d["name"]))
