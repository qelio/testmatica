"""Внутренние эндпоинты: для assessment — модули курсов, к которым педагог привязывает тесты (решение №43)."""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.internal import internal_guard

from ..config import settings
from ..deps import db
from ..models import PUBLISHED, REMOVED, Node

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(internal_guard(settings.internal_token))])


class ModulesIn(BaseModel):
    module_ids: list[UUID] = Field(max_length=200)
    user_id: UUID


class ModuleBrief(BaseModel):
    id: UUID
    title: str
    section_title: str
    course_id: UUID
    course_title: str
    course_theme: str
    course_status: str
    revision_status: str | None = Field(None, description="Статус черновика изменений курса (решение №46), если он есть")
    owner_id: UUID
    usable: bool = Field(description="Пользователь может привязать тест: курс опубликован или его (не снятый администратором)")


@router.post("/modules/lookup", response_model=list[ModuleBrief])
async def modules_lookup(body: ModulesIn, session: AsyncSession = Depends(db.session)) -> list[ModuleBrief]:
    modules = (await session.execute(select(Node).where(Node.id.in_(body.module_ids), Node.kind == "module"))).scalars().all()
    parents = {n.id: n for n in (await session.execute(
        select(Node).where(Node.id.in_({m.parent_id for m in modules} | {m.course_id for m in modules}))
    )).scalars()}
    drafts = dict((await session.execute(
        select(Node.revision_of, Node.status).where(Node.revision_of.in_({m.course_id for m in modules}))
    )).all()) if modules else {}
    out = []
    for m in modules:
        course, section = parents[m.course_id], parents[m.parent_id]
        out.append(ModuleBrief(
            id=m.id, title=m.title, section_title=section.title, course_id=course.id, course_title=course.title,
            course_theme=course.theme, course_status=course.status, revision_status=drafts.get(course.id), owner_id=course.owner_id, usable=course.status == PUBLISHED or (course.owner_id == body.user_id and course.status != REMOVED),
        ))
    return out
