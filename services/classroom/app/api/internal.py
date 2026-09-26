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
from .groups import check_group_limit

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(internal_guard(settings.internal_token))])


class GroupInfo(BaseModel):
    id: UUID
    teacher_id: UUID
    title: str
    subject: str | None
    paid: bool
    kind: str
    archived: bool
    member_ids: list[UUID]


class LinkInfo(BaseModel):
    teacher_id: UUID
    student_id: UUID
    active: bool
    paid: bool = False


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
        paid=group.paid,
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
    return LinkInfo(teacher_id=teacher_id, student_id=student_id, active=link.status == LINK_ACTIVE, paid=link.paid)


class GroupLimit(BaseModel):
    allowed: bool
    message: str | None = None


@router.get("/group-limit", response_model=GroupLimit)
async def group_limit(teacher_id: UUID = Query(), session: AsyncSession = Depends(db.session)) -> GroupLimit:
    """Можно ли педагогу завести ещё одну активную группу (лимит бесплатного тарифа) — для запуска набора в marketplace."""
    try:
        await check_group_limit(session, teacher_id)
    except ApiError as e:
        if e.code != "plan_limit":
            raise
        return GroupLimit(allowed=False, message=e.message)
    return GroupLimit(allowed=True)
