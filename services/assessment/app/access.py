"""Кто видит задачу и её ответы, кто видит решения учеников."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_MODERATOR, ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .models import PENDING, PRIVATE, PUBLISHED, REJECTED, RelLink, Task


def is_staff(p: Principal | None) -> bool:
    return p is not None and p.has_any(ROLE_MODERATOR)


async def linked(session: AsyncSession, teacher_id: UUID, student_id: UUID) -> bool:
    return await session.get(RelLink, (teacher_id, student_id)) is not None


async def can_view(session: AsyncSession, task: Task, p: Principal | None) -> bool:
    """Условие задачи: опубликованные — всем; приватные — автору, модераторам и ученикам автора."""
    if task.status == PUBLISHED:
        return True
    if p is None:
        return False
    if task.owner_id == p.user_id or is_staff(p):
        return True
    return await linked(session, task.owner_id, p.user_id)


def can_see_key(task: Task, p: Principal | None) -> bool:
    """Правильные ответы и тест-кейсы: автор, модераторы; педагоги — для опубликованных задач."""
    if p is None:
        return False
    if task.owner_id == p.user_id or is_staff(p):
        return True
    return task.status == PUBLISHED and p.has_any(ROLE_TEACHER)


def can_edit(task: Task, p: Principal) -> bool:
    return task.owner_id == p.user_id and (task.status in (PRIVATE, REJECTED) or (task.status == PUBLISHED and is_staff(p)))


async def load(session: AsyncSession, task_id: UUID, lock: bool = False) -> Task:
    task = await session.get(Task, task_id, with_for_update=lock)
    if task is None:
        raise ApiError(404, "task_not_found", "Задача не найдена")
    return task


async def viewable(session: AsyncSession, task_id: UUID, p: Principal | None) -> Task:
    task = await load(session, task_id)
    if not await can_view(session, task, p):
        raise ApiError(404, "task_not_found", "Задача не найдена")
    return task


async def editable(session: AsyncSession, task_id: UUID, p: Principal) -> Task:
    task = await load(session, task_id, lock=True)
    if task.owner_id != p.user_id:
        raise ApiError(404, "task_not_found", "Задача не найдена")
    if not can_edit(task, p):
        if task.status == PENDING:
            raise ApiError(409, "task_pending", "Задача на модерации — изменения недоступны")
        raise ApiError(403, "forbidden", "Опубликованную задачу нельзя менять — сделайте копию")
    return task


async def can_see_student_work(session: AsyncSession, p: Principal, student_id: UUID) -> bool:
    """Решения ученика видит сам ученик и его педагоги."""
    return p.user_id == student_id or await linked(session, p.user_id, student_id)
