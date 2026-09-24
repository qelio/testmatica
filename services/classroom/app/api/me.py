"""Кабинет ученика: мои педагоги, запросы на привязку, мои группы."""

from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_STUDENT, Principal
from testmatica_common.errors import ApiError

from .. import logic, people
from ..deps import auth, db, outbox
from ..models import LINK_ACTIVE, LINK_DECLINED, LINK_PENDING, Group, GroupMember, TeacherStudentLink
from ..schemas import MyGroupOut, MyTeacherOut, TeacherGroupRef

router = APIRouter(prefix="/me", tags=["me"])
student = auth.require(ROLE_STUDENT)


async def _my_groups(session: AsyncSession, student_id: UUID) -> list[Group]:
    rows = await session.execute(
        select(Group)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .where(GroupMember.student_id == student_id, GroupMember.left_at.is_(None), Group.archived_at.is_(None))
        .order_by(Group.title)
    )
    return list(rows.scalars())


@router.get("/teachers", response_model=list[MyTeacherOut])
async def my_teachers(principal: Principal = Depends(student), session: AsyncSession = Depends(db.session)):
    links = (
        await session.execute(
            select(TeacherStudentLink).where(
                TeacherStudentLink.student_id == principal.user_id,
                TeacherStudentLink.status.in_((LINK_ACTIVE, LINK_PENDING)),
            )
        )
    ).scalars().all()
    groups_by_teacher: dict[UUID, list[TeacherGroupRef]] = defaultdict(list)
    for g in await _my_groups(session, principal.user_id):
        groups_by_teacher[g.teacher_id].append(TeacherGroupRef(id=g.id, title=g.title))
    persons = await people.names(session, (link.teacher_id for link in links))
    result = [
        MyTeacherOut(
            link_id=link.id,
            teacher_id=link.teacher_id,
            full_name=persons[link.teacher_id].full_name if link.teacher_id in persons else people.UNKNOWN_NAME,
            status=link.status,
            groups=groups_by_teacher[link.teacher_id],
        )
        for link in links
    ]
    return sorted(result, key=lambda t: (t.status != LINK_PENDING, t.full_name))


@router.get("/groups", response_model=list[MyGroupOut])
async def my_groups(principal: Principal = Depends(student), session: AsyncSession = Depends(db.session)):
    groups = await _my_groups(session, principal.user_id)
    persons = await people.names(session, (g.teacher_id for g in groups))
    return [
        MyGroupOut(
            id=g.id,
            title=g.title,
            subject=g.subject,
            kind=g.kind,
            teacher_id=g.teacher_id,
            teacher_name=persons[g.teacher_id].full_name if g.teacher_id in persons else people.UNKNOWN_NAME,
        )
        for g in groups
    ]


async def _pending(session: AsyncSession, link_id: UUID, student_id: UUID) -> TeacherStudentLink:
    link = await session.get(TeacherStudentLink, link_id, with_for_update=True)
    if link is None or link.student_id != student_id or link.status != LINK_PENDING:
        raise ApiError(404, "request_not_found", "Запрос не найден или уже обработан")
    return link


@router.post("/requests/{link_id}/accept", status_code=204)
async def accept_request(
    link_id: UUID, principal: Principal = Depends(student), session: AsyncSession = Depends(db.session)
) -> None:
    link = await _pending(session, link_id, principal.user_id)
    group_id = link.pending_group_id
    await logic.activate_link(session, link.teacher_id, principal.user_id, link.source, principal.user_id)
    if group_id:
        group = await session.get(Group, group_id)
        if group is not None and group.archived_at is None:
            await logic.add_member(session, group, principal.user_id, principal.user_id)
    await session.commit()


@router.post("/requests/{link_id}/decline", status_code=204)
async def decline_request(
    link_id: UUID, principal: Principal = Depends(student), session: AsyncSession = Depends(db.session)
) -> None:
    link = await _pending(session, link_id, principal.user_id)
    link.status = LINK_DECLINED
    link.responded_at = logic.now()
    link.pending_group_id = None
    await outbox.event(
        session,
        "classroom.link.declined",
        {"link_id": str(link.id), "teacher_id": str(link.teacher_id), "student_id": str(principal.user_id),
         "student_name": await people.name_of(session, principal.user_id)},
        actor_id=principal.user_id,
    )
    await session.commit()
