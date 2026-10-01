from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError
from testmatica_common.plans import BASIC

from .. import logic, people
from ..deps import auth, db, outbox, plans, subjects
from ..models import Group, GroupMember
from ..schemas import AddMember, GroupCreate, GroupDetail, GroupOut, GroupUpdate, MemberOut, SignedOut

router = APIRouter(prefix="/groups", tags=["groups"])
teacher = auth.require(ROLE_TEACHER)


def _out(group: Group, count: int) -> GroupOut:
    return GroupOut(
        id=group.id,
        kind=group.kind,
        paid=group.paid,
        title=group.title,
        subject=group.subject,
        description=group.description,
        archived=group.archived_at is not None,
        student_count=count,
        created_at=group.created_at,
    )


def _active_members():
    return (
        select(GroupMember.group_id, func.count().label("n"))
        .where(GroupMember.left_at.is_(None))
        .group_by(GroupMember.group_id)
        .subquery()
    )


@router.get("", response_model=list[GroupOut])
async def list_groups(
    archived: bool = False,
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> list[GroupOut]:
    counts = _active_members()
    query = (
        select(Group, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.group_id == Group.id)
        .where(Group.teacher_id == principal.user_id)
        .where(Group.archived_at.is_not(None) if archived else Group.archived_at.is_(None))
        .order_by(Group.title)
    )
    return [_out(g, n) for g, n in (await session.execute(query)).all()]


async def check_group_limit(session: AsyncSession, teacher_id: UUID) -> None:
    """Бесплатный тариф — до 3 активных классов и групп; архивные не считаются. На «Базовом» — без ограничений."""
    active = await session.scalar(
        select(func.count()).select_from(Group).where(Group.teacher_id == teacher_id, Group.archived_at.is_(None))
    )
    limit = (await plans.settings())["free_max_groups"]  # задаёт администратор
    if active < limit:
        return
    if await plans.of(teacher_id) == BASIC:
        return
    raise ApiError(403, "plan_limit", f"На бесплатном тарифе — до {limit} активных классов и групп. "
                   "Отправьте ненужную группу в архив или подключите тариф «Базовый».", {"limit": limit})


@router.post("", response_model=GroupOut, status_code=201)
async def create_group(
    body: GroupCreate, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> GroupOut:
    await subjects.check(body.subject)  # предмет — из справочника модераторов
    await check_group_limit(session, principal.user_id)
    group = Group(
        teacher_id=principal.user_id,
        paid=body.paid,
        kind=body.kind,
        title=body.title,
        subject=body.subject,
        description=body.description,
    )
    session.add(group)
    await session.flush()
    await outbox.event(
        session,
        "classroom.group.created",
        {"group_id": str(group.id), "teacher_id": str(principal.user_id), "title": group.title, "paid": group.paid},
        actor_id=principal.user_id,
    )
    await session.commit()
    return _out(group, 0)


@router.get("/{group_id}", response_model=GroupDetail)
async def get_group(
    group_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> GroupDetail:
    group = await logic.owned_group(session, group_id, principal.user_id)
    rows = (
        await session.execute(
            select(GroupMember).where(GroupMember.group_id == group.id, GroupMember.left_at.is_(None))
        )
    ).scalars().all()
    persons = await people.names(session, (m.student_id for m in rows))
    members = sorted(
        (
            MemberOut(
                student_id=m.student_id,
                full_name=persons[m.student_id].full_name if m.student_id in persons else people.UNKNOWN_NAME,
                login=persons[m.student_id].login if m.student_id in persons else None,
                joined_at=m.joined_at,
            )
            for m in rows
        ),
        key=lambda m: m.full_name,
    )
    return GroupDetail(**_out(group, len(members)).model_dump(), members=members)


@router.patch("/{group_id}", response_model=GroupOut)
async def update_group(
    group_id: UUID,
    body: GroupUpdate,
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> GroupOut:
    group = await logic.owned_group(session, group_id, principal.user_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("title"):
        group.title = data["title"]
    if "subject" in data:
        if data["subject"] != group.subject:
            await subjects.check(data["subject"])
        group.subject = data["subject"]
    if "description" in data:
        group.description = data["description"] or ""
    if data.get("paid") is not None:
        # Новые занятия группы будут платными или бесплатными; уже созданные не меняются.
        group.paid = data["paid"]
    await outbox.event(
        session,
        "classroom.group.updated",
        {"group_id": str(group.id), "teacher_id": str(group.teacher_id), "title": group.title, "paid": group.paid},
        actor_id=principal.user_id,
    )
    await session.commit()
    return await _reload(session, group)


@router.post("/{group_id}/archive", response_model=GroupOut)
async def archive_group(
    group_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> GroupOut:
    group = await logic.owned_group(session, group_id, principal.user_id)
    if group.archived_at is None:
        group.archived_at = logic.now()
        await outbox.event(
            session,
            "classroom.group.archived",
            {"group_id": str(group.id), "teacher_id": str(group.teacher_id)},
            actor_id=principal.user_id,
        )
        await session.commit()
    return await _reload(session, group)


@router.post("/{group_id}/restore", response_model=GroupOut)
async def restore_group(
    group_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> GroupOut:
    group = await logic.owned_group(session, group_id, principal.user_id)
    if group.archived_at is not None:
        await check_group_limit(session, principal.user_id)
        group.archived_at = None
        await outbox.event(
            session,
            "classroom.group.restored",
            {"group_id": str(group.id), "teacher_id": str(group.teacher_id)},
            actor_id=principal.user_id,
        )
        await session.commit()
    return await _reload(session, group)


@router.post("/{group_id}/sign-out", response_model=SignedOut)
async def sign_out_group(
    group_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> SignedOut:
    """Выйти из аккаунтов всех учеников класса или группы на всех устройствах — после урока за школьными компьютерами."""
    group = await logic.owned_group(session, group_id, principal.user_id)
    ids = list((await session.execute(
        select(GroupMember.student_id).where(GroupMember.group_id == group.id, GroupMember.left_at.is_(None))
    )).scalars())
    await logic.sign_out(principal.user_id, ids)
    return SignedOut(count=len(ids))


@router.post("/{group_id}/members", status_code=204)
async def add_member(
    group_id: UUID,
    body: AddMember,
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> None:
    group = await logic.owned_group(session, group_id, principal.user_id)
    await logic.add_member(session, group, body.student_id, principal.user_id)
    await session.commit()


@router.delete("/{group_id}/members/{student_id}", status_code=204)
async def remove_member(
    group_id: UUID,
    student_id: UUID,
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> None:
    group = await logic.owned_group(session, group_id, principal.user_id)
    await logic.remove_member(session, group, student_id, principal.user_id)
    await session.commit()


async def _reload(session: AsyncSession, group: Group) -> GroupOut:
    count = await session.scalar(
        select(func.count()).where(GroupMember.group_id == group.id, GroupMember.left_at.is_(None))
    )
    return _out(group, count or 0)
