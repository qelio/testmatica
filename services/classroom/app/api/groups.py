from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError
from testmatica_common.plans import BASIC

from .. import logic, people
from ..deps import auth, db, outbox, plans, subjects
from ..models import OWNER, PERM_ADD_STUDENTS, PERM_MANAGE, Group, GroupMember, GroupShare
from ..schemas import (
    AddMember,
    GroupCreate,
    GroupDetail,
    GroupOut,
    GroupUpdate,
    MemberOut,
    ShareIn,
    ShareOut,
    SharePermissions,
    SignedOut,
)
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
    group, perms = await logic.group_access(session, group_id, principal.user_id)
    own = OWNER in perms
    full = own or PERM_MANAGE in perms
    rows = (
        await session.execute(
            select(GroupMember).where(GroupMember.group_id == group.id, GroupMember.left_at.is_(None))
        )
    ).scalars().all()
    persons = await people.names(session, [*(m.student_id for m in rows), *(m.added_by for m in rows if m.added_by)])
    members = sorted(
        (
            MemberOut(
                student_id=m.student_id,
                full_name=persons[m.student_id].full_name if m.student_id in persons else people.UNKNOWN_NAME,
                login=persons[m.student_id].login if m.student_id in persons else None,
                joined_at=m.joined_at,
                added_by=m.added_by,
                added_by_name=persons[m.added_by].full_name if m.added_by in persons else None,
                # Владелец и коллега с правом «управлять составом» убирают любых, с правом «добавлять» — своих.
                can_remove=full or (m.added_by == principal.user_id and PERM_ADD_STUDENTS in perms),
            )
            for m in rows
        ),
        key=lambda m: m.full_name,
    )
    owner = None if own else await people.name_of(session, group.teacher_id)
    shares: list[ShareOut] = []
    if own:
        rows_s = (await session.execute(select(GroupShare).where(GroupShare.group_id == group.id))).scalars().all()
        names = await people.names(session, [r.colleague_id for r in rows_s])
        shares = sorted((ShareOut(user_id=r.colleague_id, full_name=names[r.colleague_id].full_name if r.colleague_id in names
                                  else people.UNKNOWN_NAME, permissions=r.permissions or []) for r in rows_s),
                        key=lambda x: x.full_name)
    return GroupDetail(**_out(group, len(members), owner).model_dump(), members=members, shares=shares,
                       permissions=sorted(perms))


@router.post("/{group_id}/shares", response_model=GroupDetail)
async def share_group(
    group_id: UUID, body: ShareIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> GroupDetail:
    """Поделиться классом с коллегой (решение №57) с выбранными правами (№61): ученики класса становятся и его учениками.
    Уже поделились — права обновляются."""
    group = await logic.owned_group(session, group_id, principal.user_id)
    if not await are_colleagues(session, principal.user_id, body.colleague_id):
        raise ApiError(404, "colleague_not_found", "Это не ваш коллега — сначала добавьте его в «Мои коллеги»")
    existing = await session.get(GroupShare, (group.id, body.colleague_id), with_for_update=True)
    if existing is not None:
        existing.permissions = sorted(set(body.permissions))
    else:
        session.add(GroupShare(group_id=group.id, colleague_id=body.colleague_id, permissions=sorted(set(body.permissions))))
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


@router.put("/{group_id}/shares/{colleague_id}", response_model=GroupDetail)
async def set_share_permissions(
    group_id: UUID, colleague_id: UUID, body: SharePermissions, principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> GroupDetail:
    """Поменять права коллеги в классе (решение №61)."""
    group = await logic.owned_group(session, group_id, principal.user_id)
    share = await session.get(GroupShare, (group.id, colleague_id), with_for_update=True)
    if share is None:
        raise ApiError(404, "share_not_found", "Доступа к классу нет")
    share.permissions = sorted(set(body.permissions))
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
    """Название, предмет, описание — владелец и коллега с правом «управлять» (решение №61); платность — только владелец."""
    group, perms = await logic.group_with(session, group_id, principal.user_id, PERM_MANAGE)
    data = body.model_dump(exclude_unset=True)
    if data.get("paid") is not None and OWNER not in perms and data["paid"] != group.paid:
        raise ApiError(403, "forbidden", "Платность класса меняет только владелец")
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
    """Владелец добавляет своего ученика; коллега с правом (решение №61) — своего, и тот становится учеником владельца."""
    group, perms = await logic.group_with(session, group_id, principal.user_id, PERM_ADD_STUDENTS)
    await logic.add_member(session, group, body.student_id, principal.user_id,
                           colleague_id=None if OWNER in perms else principal.user_id)
    await session.commit()


@router.delete("/{group_id}/members/{student_id}", status_code=204)
async def remove_member(
    group_id: UUID,
    student_id: UUID,
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> None:
    """Убрать из класса: владелец и коллега с правом «управлять» — любого, с правом «добавлять» — только своего."""
    group, perms = await logic.group_with(session, group_id, principal.user_id, PERM_ADD_STUDENTS)
    if OWNER not in perms and PERM_MANAGE not in perms:
        member = await session.get(GroupMember, (group.id, student_id))
        if member is None or member.added_by != principal.user_id:
            raise ApiError(403, "forbidden", "Убрать можно только ученика, которого вы добавили сами")
    await logic.remove_member(session, group, student_id, principal.user_id)
    await session.commit()


async def _reload(session: AsyncSession, group: Group) -> GroupOut:
    count = await session.scalar(
        select(func.count()).where(GroupMember.group_id == group.id, GroupMember.left_at.is_(None))
    )
    return _out(group, count or 0)
