"""Внутренние эндпоинты для других сервисов (schedule и др.). Наружу не публикуются."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError
from testmatica_common.internal import internal_guard

from .. import logic
from ..config import settings
from ..deps import db
from ..models import LINK_ACTIVE, OWNER, PERMISSIONS, Group, GroupMember, GroupShare
from .colleagues import are_colleagues
from .groups import check_group_limit

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(internal_guard(settings.internal_token))])


class TeacherAccess(BaseModel):
    teacher_id: UUID
    permissions: list[str]


class GroupInfo(BaseModel):
    id: UUID
    teacher_id: UUID
    title: str
    subject: str | None
    paid: bool
    kind: str
    archived: bool
    member_ids: list[UUID]
    # Решение №61: права запросившего педагога (owner — владелец) и все педагоги класса с их правами.
    permissions: list[str] = []
    teachers: list[TeacherAccess] = []


class LinkInfo(BaseModel):
    teacher_id: UUID
    student_id: UUID
    active: bool
    paid: bool = False


@router.get("/groups/{group_id}", response_model=GroupInfo)
async def group_info(
    group_id: UUID, teacher_id: UUID = Query(), session: AsyncSession = Depends(db.session)
) -> GroupInfo:
    """Группа педагога (своя или общая с коллегой, решение №57) и её текущий состав. 404, если чужая.
    permissions — права этого педагога, teachers — владелец и коллеги с правами (решение №61)."""
    group, perms = await logic.group_access(session, group_id, teacher_id)
    shares = (await session.execute(select(GroupShare).where(GroupShare.group_id == group.id))).scalars().all()
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
        permissions=sorted(perms),
        teachers=[TeacherAccess(teacher_id=group.teacher_id, permissions=[OWNER, *PERMISSIONS])]
        + [TeacherAccess(teacher_id=s.colleague_id, permissions=sorted(logic.share_permissions(s))) for s in shares],
    )


@router.get("/teachers/{teacher_id}/groups", response_model=list[GroupInfo])
async def teacher_groups(
    teacher_id: UUID, archived: bool = Query(False), with_permission: str | None = Query(None),
    session: AsyncSession = Depends(db.session),
) -> list[GroupInfo]:
    """Группы педагога с составом — для сводной ведомости в academic. with_permission — и общие классы коллег,
    где у него есть это право (решение №61; например, class_works — для списка работ в assessment)."""
    owned = Group.teacher_id == teacher_id
    if with_permission:
        owned = or_(owned, Group.id.in_(select(GroupShare.group_id).where(
            GroupShare.colleague_id == teacher_id,
            GroupShare.permissions.contains([with_permission]))))
    query = select(Group).where(owned)
    if not archived:
        query = query.where(Group.archived_at.is_(None))
    groups = (await session.execute(query.order_by(Group.title))).scalars().all()
    members: dict[UUID, list[UUID]] = {g.id: [] for g in groups}
    if groups:
        rows = await session.execute(
            select(GroupMember.group_id, GroupMember.student_id)
            .where(GroupMember.group_id.in_(list(members)), GroupMember.left_at.is_(None))
        )
        for gid, sid in rows:
            members[gid].append(sid)
    return [
        GroupInfo(id=g.id, teacher_id=g.teacher_id, title=g.title, subject=g.subject, paid=g.paid, kind=g.kind,
                  archived=g.archived_at is not None, member_ids=members[g.id])
        for g in groups
    ]


@router.get("/links", response_model=LinkInfo)
async def link_info(
    teacher_id: UUID = Query(), student_id: UUID = Query(), session: AsyncSession = Depends(db.session)
) -> LinkInfo:
    link = await logic.get_link(session, teacher_id, student_id)
    if link is None:
        raise ApiError(404, "student_not_found", "Ученик не привязан к педагогу")
    return LinkInfo(teacher_id=teacher_id, student_id=student_id, active=link.status == LINK_ACTIVE, paid=link.paid)


class ColleagueCheck(BaseModel):
    colleagues: bool


@router.get("/colleagues/check", response_model=ColleagueCheck)
async def colleague_check(
    teacher_id: UUID = Query(), other_id: UUID = Query(), session: AsyncSession = Depends(db.session)
) -> ColleagueCheck:
    """Педагоги — коллеги (решение №56): для доступа к общим тестам в assessment."""
    return ColleagueCheck(colleagues=await are_colleagues(session, teacher_id, other_id))


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
