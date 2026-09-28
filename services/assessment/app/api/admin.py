"""Администратор снимает любую задачу с платформы без очереди модерации (ТЗ, раздел 2: «удаление любого контента»).
Задача не удаляется: в уже выданных тестах и истории решений она остаётся, из банка и у учеников автора — исчезает."""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_ADMIN, Principal
from testmatica_common.errors import ApiError

from .. import access, views
from ..deps import auth, db, outbox
from ..models import PRIVATE, PUBLISHED, REJECTED, REMOVED
from ..schemas import TaskOut

router = APIRouter(prefix="/admin", tags=["admin"])
admin = auth.require(ROLE_ADMIN)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/tasks/{task_id}/remove", response_model=TaskOut)
async def remove(task_id: UUID, body: ReasonIn, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> TaskOut:
    task = await access.load(session, task_id, lock=True)
    if task.status != REMOVED:
        task.removed_from = task.status
        task.status, task.review_comment = REMOVED, body.reason.strip()
        await outbox.event(session, "assessment.task.removed", {
            "task_id": str(task.id), "title": task.title, "author_id": str(task.owner_id), "reason": task.review_comment,
        }, actor_id=principal.user_id)
        await session.commit()
    return await views.full(session, task, principal)


@router.post("/tasks/{task_id}/restore", response_model=TaskOut)
async def restore(task_id: UUID, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> TaskOut:
    task = await access.load(session, task_id, lock=True)
    if task.status != REMOVED:
        raise ApiError(409, "not_removed", "Задача не снята с платформы")
    # Прежний статус; бывшая на проверке — в приватные (заявку из очереди уже сняли).
    task.status = task.removed_from if task.removed_from in (PUBLISHED, PRIVATE, REJECTED) else PRIVATE
    task.review_comment, task.removed_from = None, None
    await outbox.event(session, "assessment.task.restored",
                       {"task_id": str(task.id), "title": task.title, "author_id": str(task.owner_id)}, actor_id=principal.user_id)
    await session.commit()
    return await views.full(session, task, principal)
