"""Ученики педагога: три способа добавления из ТЗ (раздел 2) и управление аккаунтами."""

from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError
from testmatica_common.names import PersonName, parse_line

from .. import cards, logic, people
from ..config import settings
from ..deps import auth, db, identity, outbox
from ..models import LINK_ACTIVE, LINK_PENDING, SOURCE_MANUAL, Group, GroupMember, TeacherStudentLink
from ..schemas import (
    BulkError,
    BulkStudentsCreate,
    BulkStudentsOut,
    CardsIn,
    LinkRequestCreate,
    ManualStudentCreate,
    StudentBilling,
    StudentCredentials,
    StudentOut,
    StudentUpdate,
)

router = APIRouter(prefix="/students", tags=["students"])
teacher = auth.require(ROLE_TEACHER)


async def _students(session: AsyncSession, teacher_id: UUID, student_id: UUID | None = None) -> list[StudentOut]:
    query = select(TeacherStudentLink).where(
        TeacherStudentLink.teacher_id == teacher_id, TeacherStudentLink.status.in_((LINK_ACTIVE, LINK_PENDING))
    )
    if student_id:
        query = query.where(TeacherStudentLink.student_id == student_id)
    links = (await session.execute(query)).scalars().all()
    ids = [link.student_id for link in links]

    memberships: dict[UUID, list[UUID]] = defaultdict(list)
    if ids:
        rows = await session.execute(
            select(GroupMember.student_id, GroupMember.group_id)
            .join(Group, Group.id == GroupMember.group_id)
            .where(Group.teacher_id == teacher_id, GroupMember.student_id.in_(ids), GroupMember.left_at.is_(None))
        )
        for sid, gid in rows.all():
            memberships[sid].append(gid)

    persons = await people.names(session, ids)
    result = [
        StudentOut(
            student_id=link.student_id,
            full_name=persons[link.student_id].full_name if link.student_id in persons else people.UNKNOWN_NAME,
            login=persons[link.student_id].login if link.student_id in persons else None,
            status=link.status,
            source=link.source,
            managed=link.source == SOURCE_MANUAL,
            group_ids=memberships[link.student_id],
            paid=link.paid,
            price=link.price,
            lesson_minutes=link.lesson_minutes,
        )
        for link in links
    ]
    return sorted(result, key=lambda s: (s.status != LINK_ACTIVE, s.full_name))


async def _one(session: AsyncSession, teacher_id: UUID, student_id: UUID) -> StudentOut:
    found = await _students(session, teacher_id, student_id)
    if not found:
        raise ApiError(404, "student_not_found", "Ученик не найден")
    return found[0]


@router.get("", response_model=list[StudentOut])
async def list_students(principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)):
    return await _students(session, principal.user_id)


async def _create_managed(
    session: AsyncSession, teacher_id: UUID, name: PersonName, group: Group | None, login: str | None = None, password: str | None = None
) -> StudentCredentials:
    created = await identity.post(
        "/internal/managed-students",
        json={"teacher_id": str(teacher_id), **name.model_dump(include={"last_name", "first_name", "middle_name"}),
              "login": login, "password": password},
    )
    student_id = UUID(created["user"]["id"])
    await people.upsert_from_identity(session, created["user"])
    await logic.activate_link(session, teacher_id, student_id, SOURCE_MANUAL, teacher_id)
    if group:
        await logic.add_member(session, group, student_id, teacher_id)
    await session.commit()
    return StudentCredentials(student=await _one(session, teacher_id, student_id), login=created["login"], password=created["password"])


@router.post("/manual", response_model=StudentCredentials, status_code=201)
async def create_manual(
    body: ManualStudentCreate, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> StudentCredentials:
    """Педагог создаёт аккаунт ученика сам. Пароль показывается один раз — его надо передать ученику."""
    group = await logic.owned_group(session, body.group_id, principal.user_id) if body.group_id else None
    return await _create_managed(session, principal.user_id, body, group, body.login, body.password)


@router.post("/manual/bulk", response_model=BulkStudentsOut, status_code=201)
async def create_manual_bulk(
    body: BulkStudentsCreate, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> BulkStudentsOut:
    """Сразу несколько учеников (класс по списку): логины и пароли — автоматически. Каждый создаётся отдельно:
    если с одним не вышло, остальные всё равно создаются, ошибки — в ответе."""
    teacher_id = principal.user_id
    created, errors = [], []
    for line in body.full_names:
        try:
            name = parse_line(line)
        except ValueError as e:
            errors.append(BulkError(full_name=line, message=str(e)))
            continue
        # Группу читаем заново для каждого: после отката неудачного ученика прежний объект недействителен.
        group = await logic.owned_group(session, body.group_id, teacher_id) if body.group_id else None
        try:
            created.append(await _create_managed(session, teacher_id, name, group))
        except ApiError as e:
            await session.rollback()
            errors.append(BulkError(full_name=name.full_name, message=e.message))
    return BulkStudentsOut(created=created, errors=errors)


@router.post("/cards.pdf", response_class=Response)
async def credential_cards(body: CardsIn, principal: Principal = Depends(teacher)) -> Response:
    """PDF с карточками входа для вырезания: логин, пароль и QR-код на страницу входа.
    Пароли в системе не хранятся в открытом виде — карточки печатаются сразу после создания учеников."""
    pdf = cards.render(
        [cards.Card(full_name=s.full_name, login=s.login, password=s.password) for s in body.students],
        login_url=f"{settings.web_base_url}/login",
        title=body.title or "ТестМатика — логины и пароли учеников",
    )
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''%D0%9A%D0%B0%D1%80%D1%82%D0%BE%D1%87%D0%BA%D0%B8.pdf"})


@router.post("/requests", response_model=StudentOut, status_code=201)
async def request_link(
    body: LinkRequestCreate, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> StudentOut:
    """Привязать уже зарегистрированного ученика: он получит запрос и должен его принять."""
    group = await logic.owned_group(session, body.group_id, principal.user_id) if body.group_id else None
    found = await identity.get("/internal/users/lookup", params={"identifier": body.identifier})
    student_id = UUID(found["id"])
    if student_id == principal.user_id:
        raise ApiError(400, "self_link", "Нельзя добавить самого себя")
    if "student" not in found["roles"]:
        raise ApiError(400, "not_a_student", "Этот пользователь зарегистрирован не как ученик")
    await people.upsert_from_identity(session, found)

    link = await logic.get_link(session, principal.user_id, student_id)
    if link is not None and link.status == LINK_ACTIVE:
        if group is None:
            raise ApiError(409, "already_linked", "Ученик уже привязан к вам")
        await logic.add_member(session, group, student_id, principal.user_id)
    else:
        await logic.request_link(session, principal.user_id, student_id, group.id if group else None)
    await session.commit()
    return await _one(session, principal.user_id, student_id)


@router.patch("/{student_id}", response_model=StudentOut)
async def update_student(
    student_id: UUID,
    body: StudentUpdate,
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> StudentOut:
    await _require_managed(session, principal.user_id, student_id)
    updated = await identity.patch(
        f"/internal/managed-students/{student_id}",
        json={"teacher_id": str(principal.user_id), "name": body.name.model_dump()},
    )
    await people.upsert_from_identity(session, updated["user"])
    await session.commit()
    return await _one(session, principal.user_id, student_id)


@router.put("/{student_id}/billing", response_model=StudentOut)
async def set_billing(
    student_id: UUID,
    body: StudentBilling,
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> StudentOut:
    """Индивидуальные занятия с учеником — платные или бесплатные. Действует на новые занятия."""
    link = await logic.get_link(session, principal.user_id, student_id)
    if link is None or link.status not in (LINK_ACTIVE, LINK_PENDING):
        raise ApiError(404, "student_not_found", "Ученик не найден")
    if link.paid != body.paid:
        link.paid = body.paid
        await outbox.event(
            session, "classroom.link.billing_changed",
            {"teacher_id": str(principal.user_id), "student_id": str(student_id), "paid": body.paid}, actor_id=principal.user_id,
        )
    await session.commit()
    return await _one(session, principal.user_id, student_id)


@router.post("/{student_id}/reset-password", response_model=StudentCredentials)
async def reset_password(
    student_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> StudentCredentials:
    await _require_managed(session, principal.user_id, student_id)
    updated = await identity.patch(
        f"/internal/managed-students/{student_id}",
        json={"teacher_id": str(principal.user_id), "reset_password": True},
    )
    return StudentCredentials(
        student=await _one(session, principal.user_id, student_id),
        login=updated["login"],
        password=updated["password"],
    )


@router.delete("/{student_id}", status_code=204)
async def unlink_student(
    student_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> None:
    link = await logic.get_link(session, principal.user_id, student_id, lock=True)
    if link is None or link.status not in (LINK_ACTIVE, LINK_PENDING):
        raise ApiError(404, "student_not_found", "Ученик не найден")
    await logic.end_link(session, link, principal.user_id)
    await session.commit()


async def _require_managed(session: AsyncSession, teacher_id: UUID, student_id: UUID) -> None:
    link = await logic.active_link(session, teacher_id, student_id)
    if link.source != SOURCE_MANUAL:
        raise ApiError(403, "not_managed", "Ученик сам управляет своим аккаунтом")
