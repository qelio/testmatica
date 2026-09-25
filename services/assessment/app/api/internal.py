"""Внутренние эндпоинты для content: проверка задач, которые добавляют в модули курсов."""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.internal import internal_guard

from ..config import settings
from ..deps import db
from ..models import AUTO_TYPES, PUBLISHED, Task

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
            usable=t.owner_id == body.user_id or t.status == PUBLISHED,
        )
        for t in rows
    ]
