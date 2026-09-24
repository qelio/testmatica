"""Реакция на события других сервисов и фоновые задачи."""

import logging
from uuid import UUID

from sqlalchemy import Uuid, and_, literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from . import logic
from .deps import db
from .models import KIND_GROUP, KIND_INDIVIDUAL, STATUS_SCHEDULED, Lesson, LessonParticipant, ScheduledJob

log = logging.getLogger(__name__)


async def on_classroom_event(envelope: Envelope, session: AsyncSession) -> None:
    """Состав будущих занятий следует за составом групп и привязками."""
    data = envelope.data
    if envelope.type == "classroom.member.added":
        future = select(Lesson.id, literal(UUID(data["student_id"]), Uuid)).where(
            Lesson.group_id == UUID(data["group_id"]),
            Lesson.status == STATUS_SCHEDULED,
            Lesson.starts_at > logic.now(),
        )
        await session.execute(
            insert(LessonParticipant)
            .from_select(["lesson_id", "student_id"], future)
            .on_conflict_do_nothing()
        )
    elif envelope.type == "classroom.member.removed":
        await logic.remove_future_participation(
            session, UUID(data["student_id"]), Lesson.group_id == UUID(data["group_id"])
        )
    elif envelope.type == "classroom.link.ended":
        teacher_id, student_id = UUID(data["teacher_id"]), UUID(data["student_id"])
        # Из групповых занятий ученик уходит; индивидуальные отменяются, но остаются в его
        # календаре — он должен увидеть, что занятие отменено.
        await logic.remove_future_participation(
            session, student_id, and_(Lesson.teacher_id == teacher_id, Lesson.kind == KIND_GROUP)
        )
        individual = await session.execute(
            select(Lesson)
            .where(
                Lesson.teacher_id == teacher_id,
                Lesson.student_id == student_id,
                Lesson.kind == KIND_INDIVIDUAL,
                Lesson.status == STATUS_SCHEDULED,
                Lesson.starts_at > logic.now(),
            )
            .with_for_update()
        )
        lessons = list(individual.scalars())
        if lessons:
            await logic.cancel(session, lessons, teacher_id, "Ученик отвязан от педагога")
    elif envelope.type == "classroom.group.updated":
        await session.execute(
            update(Lesson).where(Lesson.group_id == UUID(data["group_id"])).values(group_title=data["title"])
        )


async def run_due_jobs(batch: int = 100) -> int:
    """Выполнить созревшие напоминания. Устаревшие (занятие отменено или перенесено) просто закрываются."""
    async with db.sessionmaker() as session, session.begin():
        jobs = (
            await session.execute(
                select(ScheduledJob)
                .where(ScheduledJob.done_at.is_(None), ScheduledJob.run_at <= logic.now())
                .order_by(ScheduledJob.run_at)
                .limit(batch)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        for job in jobs:
            job.attempts += 1
            job.done_at = logic.now()
            lesson = await session.get(Lesson, job.lesson_id)
            if lesson is None or lesson.status != STATUS_SCHEDULED or lesson.starts_at != job.lesson_starts_at:
                continue
            await logic.publish(
                session, "schedule.lesson.reminder", [lesson], lesson.teacher_id, {"hours": job.payload.get("hours")}
            )
        return len(jobs)
