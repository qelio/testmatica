from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError
from testmatica_common.plans import BASIC

from .. import logic, people
from ..deps import auth, db, outbox, plans, subjects
from ..models import Group, GroupMember, GroupShare
from ..schemas import AddMember, GroupCreate, GroupDetail, GroupOut, GroupUpdate, MemberOut, ShareIn, ShareOut, SignedOut
from .colleagues import are_colleagues

router = APIRouter(prefix="/groups", tags=["groups"])
teacher = auth.require(ROLE_TEACHER)


def _out(group: Group, count: int, owner_name: str | None = None) -> GroupOut:
    return GroupOut(
        shared=owner_name is not None,
        owner_name=owner_name,
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
    """Свои классы и классы, которыми поделились коллеги (решение №57) — с пометкой и именем владельца."""
    counts = _active_members()
    shared_ids = select(GroupShare.group_id).where(GroupShare.colleague_id == principal.user_id)
    query = (
        select(Group, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.group_id == Group.id)
        .where(or_(Group.teacher_id == principal.user_id, Group.id.in_(shared_ids)))
        .where(Group.archived_at.is_not(None) if archived else Group.archived_at.is_(None))
        .order_by(Group.title)
    )
    rows = (await session.execute(query)).all()
    owners = await people.names(session, {g.teacher_id for g, _ in rows if g.teacher_id != principal.user_id})
    return [
        _out(g, n, None if g.teacher_id == principal.user_id else (owners[g.teacher_id].full_name if g.teacher_id in owners else people.UNKNOWN_NAME))
        for g, n in rows
    ]


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
    group, own = await logic.readable_group(session, group_id, principal.user_id)
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
    owner = None if own else await people.name_of(session, group.teacher_id)
    shares: list[ShareOut] = []
    if own:
        ids = list((await session.execute(select(GroupShare.colleague_id).where(GroupShare.group_id == group.id))).scalars())
        names = await people.names(session, ids)
        shares = sorted((ShareOut(user_id=i, full_name=names[i].full_name if i in names else people.UNKNOWN_NAME) for i in ids),
                        key=lambda x: x.full_name)
    return GroupDetail(**_out(group, len(members), owner).model_dump(), members=members, shares=shares)


@router.post("/{group_id}/shares", response_model=GroupDetail)
async def share_group(
    group_id: UUID, body: ShareIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> GroupDetail:
    """Поделиться классом с коллегой (решение №57): ученики класса становятся и его учениками."""
    group = await logic.owned_group(session, group_id, principal.user_id)
    if not await are_colleagues(session, principal.user_id, body.colleague_id):
        raise ApiError(404, "colleague_not_found", "Это не ваш коллега — сначала добавьте его в «Мои коллеги»")
    if await session.get(GroupShare, (group.id, body.colleague_id)) is None:
        session.add(GroupShare(group_id=group.id, colleague_id=body.colleague_id))
        await session.flush()
        members = list((await session.execute(
            select(GroupMember.student_id).where(GroupMember.group_id == group.id, GroupMember.left_at.is_(None))
        )).scalars())
        await logic.refresh_colleague_links(session, body.colleague_id, members, principal.user_id)
        await outbox.event(
            session, "classroom.group.shared",
            {"group_id": str(group.id), "title": group.title, "teacher_id": str(principal.user_id),
             "teacher_name": await people.name_of(session, principal.user_id), "colleague_id": str(body.colleague_id)},
            actor_id=principal.user_id,
        )
    await session.commit()
    return await get_group(group_id, principal, session)


@router.delete("/{group_id}/shares/{colleague_id}", status_code=204)
async def unshare_group(
    group_id: UUID, colleague_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> None:
    """Закрыть доступ коллеге (владелец) или отказаться от класса (сам коллега). Сделанное коллегой остаётся,
    ученики класса перестают быть его учениками (если не занимаются у него и так)."""
    group = await session.get(Group, group_id)
    share = await session.get(GroupShare, (group_id, colleague_id), with_for_update=True)
    if group is None or share is None or principal.user_id not in (group.teacher_id, colleague_id):
        raise ApiError(404, "share_not_found", "Доступа к классу нет")
    await logic.unshare(session, share, principal.user_id)
    await session.commit()



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
