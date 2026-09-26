"""Переименование предмета в справочнике (content.subject.updated): обновить сохранённые названия."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from . import profiles
from .models import LessonRequest, TutorProfile


async def on_subject_updated(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    sid = UUID(d["subject_id"])
    profiles._subjects_cache = (0.0, {})
    await session.execute(update(LessonRequest).where(LessonRequest.subject_id == sid).values(subject_name=d["name"]))
    rows = (await session.execute(select(TutorProfile).where(TutorProfile.subject_ids.contains([sid])).with_for_update())).scalars()
    for p in rows:
        p.subjects = [s | {"name": d["name"]} if s["id"] == str(sid) else s for s in p.subjects]
