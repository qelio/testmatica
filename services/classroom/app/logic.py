"""Операции над группами и привязками. Все события публикуются здесь, в той же транзакции."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError

from .deps import outbox
from .models import LINK_ACTIVE, LINK_ENDED, LINK_PENDING, Group, GroupMember, TeacherStudentLink
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


async def add_member(session: AsyncSession, group: Group, student_id: UUID, actor_id: UUID) -> None:
    if group.archived_at is not None:
        raise ApiError(409, "group_archived", "Группа в архиве")
    await active_link(session, group.teacher_id, student_id)
    member = await session.get(GroupMember, (group.id, student_id), with_for_update=True)
    if member is not None and member.left_at is None:
        return
    if member is None:
        session.add(GroupMember(group_id=group.id, student_id=student_id, joined_at=now()))
    else:
        member.left_at = None
        member.joined_at = now()
    await session.flush()
    await outbox.event(
        session,
        "classroom.member.added",
        {"group_id": str(group.id), "teacher_id": str(group.teacher_id), "student_id": str(student_id)},
        actor_id=actor_id,
    )


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
