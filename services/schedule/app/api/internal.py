"""Внутренние эндпоинты для других сервисов (academic и др.). Наружу не публикуются."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError
from testmatica_common.internal import internal_guard

from .. import logic
from ..config import settings
from ..deps import db
from ..models import Lesson

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(internal_guard(settings.internal_token))])


class LessonInfo(BaseModel):
    id: UUID
    teacher_id: UUID
    kind: str
    paid: bool
    group_id: UUID | None
    student_id: UUID | None
    subject: str | None
    topic: str | None
    starts_at: datetime
    ends_at: datetime
    status: str
    participant_ids: list[UUID]
    group_title: str | None = None
    video_url: str | None = None


async def _info(session: AsyncSession, lessons: list[Lesson]) -> list[LessonInfo]:
    participants = await logic.participant_ids(session, [lesson.id for lesson in lessons])
    return [
        LessonInfo(
            id=lesson.id,
            teacher_id=lesson.teacher_id,
            kind=lesson.kind,
            paid=lesson.paid,
            group_id=lesson.group_id,
            student_id=lesson.student_id,
            subject=lesson.subject,
            topic=lesson.topic,
            starts_at=lesson.starts_at,
            ends_at=lesson.ends_at,
            status=lesson.status,
            participant_ids=participants[lesson.id],
            group_title=lesson.group_title,
            video_url=lesson.video_url,
        )
        for lesson in lessons
    ]


@router.get("/lessons", response_model=list[LessonInfo])
async def lessons(
    teacher_id: UUID = Query(),
    group_id: UUID | None = None,
    student_id: UUID | None = None,
    start: datetime = Query(alias="from"),
    end: datetime = Query(alias="to"),
    all_teachers: bool = Query(False, description="Занятия группы всех педагогов — для общего журнала класса (решение №59)"),
    session: AsyncSession = Depends(db.session),
) -> list[LessonInfo]:
    """Занятия педагога за период: группы (group_id) или индивидуальные с учеником (student_id).
    all_teachers — занятия группы у всех педагогов (доступ к группе проверяет вызывающий сервис)."""
    if (group_id is None) == (student_id is None):
        raise ApiError(422, "invalid_target", "Нужен ровно один параметр: group_id или student_id")
    query = select(Lesson).where(Lesson.starts_at >= start, Lesson.starts_at < end)
    if not (all_teachers and group_id):
        query = query.where(Lesson.teacher_id == teacher_id)
    query = query.where(Lesson.group_id == group_id) if group_id else query.where(Lesson.student_id == student_id)
    rows = (await session.execute(query.order_by(Lesson.starts_at))).scalars().all()
    return await _info(session, list(rows))


@router.get("/lessons/{lesson_id}", response_model=LessonInfo)
async def lesson(lesson_id: UUID, teacher_id: UUID = Query(), session: AsyncSession = Depends(db.session)) -> LessonInfo:
    found = await session.get(Lesson, lesson_id)
    if found is None or found.teacher_id != teacher_id:
        raise ApiError(404, "lesson_not_found", "Занятие не найдено")
    return (await _info(session, [found]))[0]


@router.get("/lessons/{lesson_id}/room", response_model=LessonInfo)
async def lesson_for_room(lesson_id: UUID, session: AsyncSession = Depends(db.session)) -> LessonInfo:
    """Занятие для видеокомнаты: сервис video сам проверяет, педагог это или участник."""
    found = await session.get(Lesson, lesson_id)
    if found is None:
        raise ApiError(404, "lesson_not_found", "Занятие не найдено")
    return (await _info(session, [found]))[0]
