"""Занятие удалили из расписания (решение №54): его оценки и посещаемость в журнале удаляются, урок КТП отвязывается."""

from uuid import UUID

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .models import Attendance, Grade, PlanLesson


async def on_schedule_event(envelope: Envelope, session: AsyncSession) -> None:
    if envelope.type != "schedule.lesson.deleted":
        return
    ids = [UUID(x) for x in envelope.data.get("lesson_ids", [])]
    if not ids:
        return
    await session.execute(delete(Grade).where(Grade.lesson_id.in_(ids)))
    await session.execute(delete(Attendance).where(Attendance.lesson_id.in_(ids)))
    await session.execute(update(PlanLesson).where(PlanLesson.schedule_lesson_id.in_(ids)).values(schedule_lesson_id=None))
