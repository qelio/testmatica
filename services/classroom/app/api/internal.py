"""Внутренние эндпоинты для других сервисов (schedule и др.). Наружу не публикуются."""

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
from ..models import LINK_ACTIVE, GroupMember

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(internal_guard(settings.internal_token))])


class GroupInfo(BaseModel):
    id: UUID
    teacher_id: UUID
    title: str
    subject: str | None
    mode: str
    kind: str
    archived: bool
    member_ids: list[UUID]


class LinkInfo(BaseModel):
    teacher_id: UUID
    student_id: UUID
    active: bool


@router.get("/groups/{group_id}", response_model=GroupInfo)
async def group_info(
    group_id: UUID, teacher_id: UUID = Query(), session: AsyncSession = Depends(db.session)
) -> GroupInfo:
    """Группа педагога и её текущий состав. 404, если группа чужая."""
    group = await logic.owned_group(session, group_id, teacher_id)
    members = await session.execute(
        select(GroupMember.student_id).where(GroupMember.group_id == group.id, GroupMember.left_at.is_(None))
    )
    return GroupInfo(
        id=group.id,
        teacher_id=group.teacher_id,
        title=group.title,
        subject=group.subject,
        mode=group.mode,
        kind=group.kind,
        archived=group.archived_at is not None,
        member_ids=list(members.scalars()),
    )


@router.get("/links", response_model=LinkInfo)
async def link_info(
    teacher_id: UUID = Query(), student_id: UUID = Query(), session: AsyncSession = Depends(db.session)
) -> LinkInfo:
    link = await logic.get_link(session, teacher_id, student_id)
    if link is None:
        raise ApiError(404, "student_not_found", "Ученик не привязан к педагогу")
    return LinkInfo(teacher_id=teacher_id, student_id=student_id, active=link.status == LINK_ACTIVE)
