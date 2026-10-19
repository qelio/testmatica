"""Планировщик педагога (решение №54): дела по дням с отметкой «выполнено»."""

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from ..deps import auth, db
from ..models import TeacherTask
from ..schemas import TeacherTaskIn, TeacherTaskOut, TeacherTaskUpdate

router = APIRouter(prefix="/todos", tags=["todos"])
teacher = auth.require(ROLE_TEACHER)
MAX_RANGE_DAYS = 120


async def _own(session: AsyncSession, task_id: UUID, p: Principal) -> TeacherTask:
    task = await session.get(TeacherTask, task_id, with_for_update=True)
    if task is None or task.teacher_id != p.user_id:
        raise ApiError(404, "todo_not_found", "Задача не найдена")
    return task


@router.get("", response_model=list[TeacherTaskOut])
async def list_todos(
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> list[TeacherTask]:
    """Дела за дни from…to включительно (не больше 120 дней) — по дням, невыполненные первыми."""
    if date_to < date_from or (date_to - date_from).days > MAX_RANGE_DAYS:
        raise ApiError(422, "invalid_range", f"Период — от 1 до {MAX_RANGE_DAYS} дней")
    rows = await session.execute(
        select(TeacherTask)
        .where(TeacherTask.teacher_id == principal.user_id, TeacherTask.day >= date_from, TeacherTask.day <= date_to)
        .order_by(TeacherTask.day, TeacherTask.done, TeacherTask.created_at)
    )
    return list(rows.scalars())


@router.post("", response_model=TeacherTaskOut, status_code=201)
async def create_todo(body: TeacherTaskIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> TeacherTask:
    task = TeacherTask(teacher_id=principal.user_id, day=body.day, title=body.title.strip())
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TeacherTaskOut)
async def update_todo(
    task_id: UUID, body: TeacherTaskUpdate, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> TeacherTask:
    """Выполнено / не выполнено, другой текст или перенос на другой день."""
    task = await _own(session, task_id, principal)
    if body.title is not None:
        task.title = body.title.strip()
    if body.day is not None:
        task.day = body.day
    if body.done is not None and body.done != task.done:
        task.done, task.done_at = body.done, datetime.now(UTC) if body.done else None
    await session.commit()
    await session.refresh(task)
    return task


@router.delete("/{task_id}", status_code=204)
async def delete_todo(task_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> None:
    await session.delete(await _own(session, task_id, principal))
    await session.commit()
