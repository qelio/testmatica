"""Операции над группами и привязками. Все события публикуются здесь, в той же транзакции."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError

from .deps import identity, outbox
from .models import (
    LINK_ACTIVE,
    LINK_ENDED,
    LINK_PENDING,
    OWNER,
    PERM_ADD_STUDENTS,
    PERM_MANAGE,
    PERMISSIONS,
    SOURCE_COLLEAGUE,
    Group,
    GroupMember,
    GroupShare,
    TeacherStudentLink,
)
from .people import name_of


def now() -> datetime:
    return datetime.now(UTC)


async def owned_group(session: AsyncSession, group_id: UUID, teacher_id: UUID) -> Group:
    group = await session.get(Group, group_id)
    if group is None or group.teacher_id != teacher_id:
        raise ApiError(404, "group_not_found", "Группа не найдена")
    return group


async def get_link(session: AsyncSession, teacher_id: UUID, student_id: UUID, lock: bool = False) -> TeacherStudentLink | None:
    query = select(TeacherStudentLink).where(
        TeacherStudentLink.teacher_id == teacher_id, TeacherStudentLink.student_id == student_id
    )
    if lock:
        query = query.with_for_update()
    return (await session.execute(query)).scalar_one_or_none()


async def sign_out(teacher_id: UUID, student_ids: list[UUID]) -> None:
    """Выйти из аккаунтов учеников на всех устройствах (оставили вход на школьном компьютере)."""
    if student_ids:
        await identity.post("/internal/sessions/sign-out",
                            json={"teacher_id": str(teacher_id), "user_ids": [str(s) for s in student_ids]})


async def active_link(session: AsyncSession, teacher_id: UUID, student_id: UUID) -> TeacherStudentLink:
    link = await get_link(session, teacher_id, student_id)
    if link is None or link.status != LINK_ACTIVE:
        raise ApiError(404, "student_not_found", "Ученик не привязан к вам")
    return link


async def activate_link(
    session: AsyncSession, teacher_id: UUID, student_id: UUID, source: str, actor_id: UUID
) -> TeacherStudentLink:
    """Создать или восстановить активную привязку."""
    link = await get_link(session, teacher_id, student_id, lock=True)
    if link is None:
        link = TeacherStudentLink(teacher_id=teacher_id, student_id=student_id, status=LINK_ACTIVE, source=source)
        session.add(link)
    elif link.status == LINK_ACTIVE:
        return link
    else:
        link.status = LINK_ACTIVE
        link.source = source
    link.responded_at = now()
    link.pending_group_id = None
    await session.flush()
    await outbox.event(
        session,
        "classroom.link.created",
        {
            "link_id": str(link.id),
            "teacher_id": str(teacher_id),
            "student_id": str(student_id),
            "source": source,
            "student_name": await name_of(session, student_id),
        },
        actor_id=actor_id,
    )
    return link


async def request_link(
    session: AsyncSession, teacher_id: UUID, student_id: UUID, group_id: UUID | None
) -> TeacherStudentLink:
    """Запрос на привязку уже зарегистрированного ученика: ждёт его подтверждения."""
    link = await get_link(session, teacher_id, student_id, lock=True)
    if link is not None and link.status == LINK_ACTIVE:
        raise ApiError(409, "already_linked", "Ученик уже привязан к вам")
    if link is None:
        link = TeacherStudentLink(teacher_id=teacher_id, student_id=student_id, source="request", status=LINK_PENDING)
        session.add(link)
    link.status = LINK_PENDING
    link.source = "request"
    link.pending_group_id = group_id
    link.responded_at = None
    await session.flush()
    await outbox.event(
        session,
        "classroom.link.requested",
        {
            "link_id": str(link.id),
            "teacher_id": str(teacher_id),
            "student_id": str(student_id),
            "teacher_name": await name_of(session, teacher_id),
        },
        actor_id=teacher_id,
    )
    return link


async def end_link(session: AsyncSession, link: TeacherStudentLink, actor_id: UUID) -> None:
    """Отвязать ученика: он выходит из всех групп этого педагога."""
    link.status = LINK_ENDED
    link.responded_at = now()
    teacher_groups = select(Group.id).where(Group.teacher_id == link.teacher_id)
    await session.execute(
        update(GroupMember)
        .where(
            GroupMember.student_id == link.student_id,
            GroupMember.group_id.in_(teacher_groups),
            GroupMember.left_at.is_(None),
        )
        .values(left_at=now())
    )
    await outbox.event(
        session,
        "classroom.link.ended",
        {"link_id": str(link.id), "teacher_id": str(link.teacher_id), "student_id": str(link.student_id)},
        actor_id=actor_id,
    )
    # Ученик вышел из классов педагога — и у коллег, с которыми ими поделились, он больше не ученик.
    if link.source != SOURCE_COLLEAGUE:
        await session.flush()
        owned = list((await session.execute(select(Group.id).where(Group.teacher_id == link.teacher_id))).scalars())
        await refresh_shared(session, owned, [link.student_id], actor_id)


async def readable_group(session: AsyncSession, group_id: UUID, teacher_id: UUID) -> tuple[Group, bool]:
    """Свой класс или класс, которым поделился коллега (решение №57). Второе — True, если свой."""
    group = await session.get(Group, group_id)
    if group is not None and group.teacher_id == teacher_id:
        return group, True
    if group is not None and await session.get(GroupShare, (group_id, teacher_id)) is not None:
        return group, False
    raise ApiError(404, "group_not_found", "Группа не найдена")


def share_permissions(share: GroupShare) -> set[str]:
    perms = set(share.permissions or [])
    if PERM_MANAGE in perms:
        perms.add(PERM_ADD_STUDENTS)  # управляет составом — может и добавлять своих
    return perms


async def group_access(session: AsyncSession, group_id: UUID, teacher_id: UUID) -> tuple[Group, set[str]]:
    """Класс и права педагога в нём (решение №61): владелец — всё (owner), коллега — права доступа. 404 — нет доступа."""
    group = await session.get(Group, group_id)
    if group is not None and group.teacher_id == teacher_id:
        return group, {OWNER, *PERMISSIONS}
    share = await session.get(GroupShare, (group_id, teacher_id)) if group is not None else None
    if share is None:
        raise ApiError(404, "group_not_found", "Группа не найдена")
    return group, share_permissions(share)


async def group_with(session: AsyncSession, group_id: UUID, teacher_id: UUID, *need: str) -> tuple[Group, set[str]]:
    """Класс, если у педагога есть хотя бы одно из прав need (владелец — всегда)."""
    group, perms = await group_access(session, group_id, teacher_id)
    if OWNER not in perms and not perms & set(need):
        raise ApiError(403, "forbidden", "У вас нет такого права в этом классе — его даёт владелец класса")
    return group, perms


async def refresh_owner_link(session: AsyncSession, owner_id: UUID, student_id: UUID, actor_id: UUID) -> None:
    """Ученик пришёл к владельцу через класс от коллеги (source=colleague) и больше не в его классах — связь закрывается."""
    link = await get_link(session, owner_id, student_id, lock=True)
    if link is None or link.status != LINK_ACTIVE or link.source != SOURCE_COLLEAGUE:
        return
    in_classes = await session.scalar(
        select(func.count()).select_from(GroupMember).join(Group, Group.id == GroupMember.group_id)
        .where(Group.teacher_id == owner_id, GroupMember.student_id == student_id, GroupMember.left_at.is_(None))
    )
    if not in_classes:
        await end_link(session, link, actor_id)


async def group_colleagues(session: AsyncSession, group_ids: list[UUID]) -> list[UUID]:
    if not group_ids:
        return []
    rows = await session.execute(select(GroupShare.colleague_id).where(GroupShare.group_id.in_(group_ids)).distinct())
    return list(rows.scalars())


async def refresh_colleague_links(session: AsyncSession, colleague_id: UUID, student_ids: list[UUID], actor_id: UUID) -> None:
    """Ученики общих классов — ученики коллеги (решение №57): есть в классе, которым с ним поделились, — связь
    активна; больше нет — связь «от коллеги» закрывается (свои ученики коллеги не трогаются)."""
    for student_id in student_ids:
        covered = await session.scalar(
            select(func.count()).select_from(GroupShare)
            .join(GroupMember, GroupMember.group_id == GroupShare.group_id)
            .where(GroupShare.colleague_id == colleague_id, GroupMember.student_id == student_id, GroupMember.left_at.is_(None))
        )
        link = await get_link(session, colleague_id, student_id, lock=True)
        if covered:
            if link is None or link.status != LINK_ACTIVE:
                await activate_link(session, colleague_id, student_id, SOURCE_COLLEAGUE, actor_id)
        elif link is not None and link.status == LINK_ACTIVE and link.source == SOURCE_COLLEAGUE:
            await end_link(session, link, actor_id)


async def refresh_shared(session: AsyncSession, group_ids: list[UUID], student_ids: list[UUID], actor_id: UUID) -> None:
    """Состав общих классов изменился — обновить учеников у коллег, с которыми ими поделились."""
    for colleague_id in await group_colleagues(session, group_ids):
        await refresh_colleague_links(session, colleague_id, student_ids, actor_id)


async def unshare(session: AsyncSession, share: GroupShare, actor_id: UUID) -> None:
    """Закрыть коллеге доступ к классу: сделанное им остаётся, ученики класса перестают быть его (если не свои)."""
    members = list((await session.execute(
        select(GroupMember.student_id).where(GroupMember.group_id == share.group_id, GroupMember.left_at.is_(None))
    )).scalars())
    await session.delete(share)
    await session.flush()
    await refresh_colleague_links(session, share.colleague_id, members, actor_id)


async def add_member(
    session: AsyncSession, group: Group, student_id: UUID, actor_id: UUID, colleague_id: UUID | None = None
) -> None:
    """Добавить в класс. Добавляет коллега (решение №61) — ученик должен быть его, и он становится учеником владельца."""
    if group.archived_at is not None:
        raise ApiError(409, "group_archived", "Группа в архиве")
    by_colleague = colleague_id is not None
    if by_colleague:
        link = await active_link(session, colleague_id, student_id)
        if link.source == SOURCE_COLLEAGUE:
            raise ApiError(409, "not_own_student", "Добавить можно только своего ученика")
        owner_link = await get_link(session, group.teacher_id, student_id)
        if owner_link is None or owner_link.status != LINK_ACTIVE:
            await activate_link(session, group.teacher_id, student_id, SOURCE_COLLEAGUE, actor_id)
    else:
        await active_link(session, group.teacher_id, student_id)
    member = await session.get(GroupMember, (group.id, student_id), with_for_update=True)
    if member is not None and member.left_at is None:
        return
    if member is None:
        session.add(GroupMember(group_id=group.id, student_id=student_id, joined_at=now(), added_by=colleague_id))
    else:
        member.left_at = None
        member.joined_at = now()
        member.added_by = colleague_id
    await session.flush()
    await outbox.event(
        session,
        "classroom.member.added",
        {"group_id": str(group.id), "teacher_id": str(group.teacher_id), "student_id": str(student_id)},
        actor_id=actor_id,
    )
    await refresh_shared(session, [group.id], [student_id], actor_id)


async def remove_member(session: AsyncSession, group: Group, student_id: UUID, actor_id: UUID) -> None:
    member = await session.get(GroupMember, (group.id, student_id), with_for_update=True)
    if member is None or member.left_at is not None:
        raise ApiError(404, "member_not_found", "Ученика нет в этой группе")
    member.left_at = now()
    await outbox.event(
        session,
        "classroom.member.removed",
        {"group_id": str(group.id), "teacher_id": str(group.teacher_id), "student_id": str(student_id)},
        actor_id=actor_id,
    )
    await session.flush()
    await refresh_shared(session, [group.id], [student_id], actor_id)
    await refresh_owner_link(session, group.teacher_id, student_id, actor_id)
