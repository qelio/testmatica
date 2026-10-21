"""Внутренние эндпоинты: для content — проверка задач в модулях курсов; для video — доступ к прокторингу."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError
from testmatica_common.internal import internal_guard

from .. import views
from ..config import settings
from ..deps import db
from ..models import AUTO_TYPES, IN_PROGRESS, PUBLISHED, REMOVED, Assignment, Attempt, Task
from ..schemas import ProctorAccess, ProctorStudent

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(internal_guard(settings.internal_token))])


class LookupIn(BaseModel):
    task_ids: list[UUID] = Field(max_length=500)
    user_id: UUID


class TaskBrief(BaseModel):
    id: UUID
    title: str
    type: str
    status: str
    owner_id: UUID
    auto_checked: bool
    usable: bool = Field(description="Пользователь может добавить задачу в свой курс: своя или опубликованная")


@router.post("/tasks/lookup", response_model=list[TaskBrief])
async def lookup(body: LookupIn, session: AsyncSession = Depends(db.session)) -> list[TaskBrief]:
    rows = (await session.execute(select(Task).where(Task.id.in_(body.task_ids)))).scalars()
    return [
        TaskBrief(
            id=t.id, title=t.title, type=t.type, status=t.status, owner_id=t.owner_id, auto_checked=t.type in AUTO_TYPES,
            usable=(t.owner_id == body.user_id or t.status == PUBLISHED) and t.status != REMOVED,
        )
        for t in rows
    ]


class SubjectsIn(BaseModel):
    assignment_ids: list[UUID] = Field(max_length=1000)


@router.post("/assignments/subjects", response_model=dict[UUID, str | None])
async def assignment_subjects(body: SubjectsIn, session: AsyncSession = Depends(db.session)) -> dict[UUID, str | None]:
    """Предметы работ — academic разносит по журналам предметов старые оценки за тесты (решение №59)."""
    rows = await session.execute(select(Assignment.id, Assignment.subject_name).where(Assignment.id.in_(body.assignment_ids)))
    return dict(rows.all())


@router.get("/proctoring/{assignment_id}", response_model=ProctorAccess)
async def proctoring_access(assignment_id: UUID, user_id: UUID = Query(), session: AsyncSession = Depends(db.session)) -> ProctorAccess:
    """Кто пользователь в прокторинге: педагог назначения или ученик с идущей попыткой. Остальным — 404."""
    a = await session.get(Assignment, assignment_id)
    if a is None or not a.proctoring:
        raise ApiError(404, "assignment_not_found", "Тест с прокторингом не найден")
    open_attempts = {t.student_id: t.id for t in (await session.execute(
        select(Attempt).where(Attempt.assignment_id == a.id, Attempt.status == IN_PROGRESS)
    )).scalars()}
    base = {"assignment_id": a.id, "teacher_id": a.teacher_id, "title": a.title, "closed": a.closed_at is not None}
    if a.teacher_id == user_id:
        ids = [r.student_id for r in a.students]
        names = await views.names(session, ids)
        students = sorted((ProctorStudent(id=i, full_name=names.get(i, "Ученик"), attempt_id=open_attempts.get(i)) for i in ids),
                          key=lambda s: s.full_name)
        return ProctorAccess(role="teacher", students=students, **base)
    if any(r.student_id == user_id for r in a.students):
        return ProctorAccess(role="student", attempt_id=open_attempts.get(user_id), **base)
    raise ApiError(404, "assignment_not_found", "Тест с прокторингом не найден")
