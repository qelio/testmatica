"""Мои коллеги (решение №56): педагоги добавляют друг друга по логину или почте — заявка, коллега принимает.
Коллеге можно дать доступ к своему классу и тесту (следующие этапы)."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import logic, people
from ..deps import auth, db, identity, outbox
from ..models import COLLEAGUE_ACTIVE, COLLEAGUE_PENDING, Colleague, Group, GroupShare
from ..schemas import ColleagueOut, ColleagueRequestIn, ColleagueRequestOut, ColleaguesOut

router = APIRouter(prefix="/colleagues", tags=["colleagues"])
teacher = auth.require(ROLE_TEACHER)


async def pair(session: AsyncSession, a: UUID, b: UUID, lock: bool = False) -> Colleague | None:
    """Связь двух педагогов в любую сторону."""
    query = select(Colleague).where(
        or_((Colleague.requester_id == a) & (Colleague.addressee_id == b), (Colleague.requester_id == b) & (Colleague.addressee_id == a))
    )
    return await session.scalar(query.with_for_update() if lock else query)


async def are_colleagues(session: AsyncSession, a: UUID, b: UUID) -> bool:
    found = await pair(session, a, b)
    return found is not None and found.status == COLLEAGUE_ACTIVE


async def _event(session: AsyncSession, type_: str, c: Colleague, actor: UUID, to: UUID) -> None:
    await outbox.event(
        session, type_,
        {"request_id": str(c.id), "requester_id": str(c.requester_id), "addressee_id": str(c.addressee_id),
         "actor_name": await people.name_of(session, actor), "to_id": str(to)},
        actor_id=actor,
    )


@router.get("", response_model=ColleaguesOut)
async def list_colleagues(principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> ColleaguesOut:
    me = principal.user_id
    rows = (await session.execute(
        select(Colleague).where(or_(Colleague.requester_id == me, Colleague.addressee_id == me)).order_by(Colleague.created_at.desc())
    )).scalars().all()
    other = {c.id: c.addressee_id if c.requester_id == me else c.requester_id for c in rows}
    names = await people.names(session, list(other.values()))

    def person(uid: UUID) -> tuple[str, str | None]:
        p = names.get(uid)
        return (p.full_name, p.login) if p else (people.UNKNOWN_NAME, None)

    colleagues, incoming, outgoing = [], [], []
    for c in rows:
        uid = other[c.id]
        name, login = person(uid)
        if c.status == COLLEAGUE_ACTIVE:
            colleagues.append(ColleagueOut(user_id=uid, full_name=name, login=login, since=c.responded_at or c.created_at))
        else:
            item = ColleagueRequestOut(id=c.id, user_id=uid, full_name=name, login=login, created_at=c.created_at)
            (incoming if c.addressee_id == me else outgoing).append(item)
    colleagues.sort(key=lambda x: x.full_name.lower())
    return ColleaguesOut(colleagues=colleagues, incoming=incoming, outgoing=outgoing)


@router.post("", response_model=ColleaguesOut, status_code=201)
async def request_colleague(
    body: ColleagueRequestIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> ColleaguesOut:
    """Заявка педагогу по логину или почте. Он уже прислал заявку вам — вы сразу становитесь коллегами."""
    found = await identity.get("/internal/users/lookup", params={"identifier": body.identifier.strip()})
    other = UUID(found["id"])
    if other == principal.user_id:
        raise ApiError(400, "self_colleague", "Нельзя добавить в коллеги самого себя")
    if "teacher" not in found["roles"]:
        raise ApiError(400, "not_a_teacher", "Этот пользователь зарегистрирован не как педагог")
    await people.upsert_from_identity(session, found)
    existing = await pair(session, principal.user_id, other, lock=True)
    if existing is not None and existing.status == COLLEAGUE_ACTIVE:
        raise ApiError(409, "already_colleagues", "Вы уже коллеги")
    if existing is not None and existing.requester_id == principal.user_id:
        raise ApiError(409, "already_requested", "Заявка уже отправлена — ждём ответа коллеги")
    if existing is not None:  # встречная заявка — принимаем
        existing.status, existing.responded_at = COLLEAGUE_ACTIVE, datetime.now(UTC)
        await _event(session, "classroom.colleague.accepted", existing, principal.user_id, other)
    else:
        c = Colleague(requester_id=principal.user_id, addressee_id=other, status=COLLEAGUE_PENDING)
        session.add(c)
        await session.flush()
        await _event(session, "classroom.colleague.requested", c, principal.user_id, other)
    await session.commit()
    return await list_colleagues(principal, session)


async def _incoming(session: AsyncSession, request_id: UUID, p: Principal) -> Colleague:
    c = await session.get(Colleague, request_id, with_for_update=True)
    if c is None or c.addressee_id != p.user_id or c.status != COLLEAGUE_PENDING:
        raise ApiError(404, "request_not_found", "Заявка не найдена")
    return c


@router.post("/requests/{request_id}/accept", response_model=ColleaguesOut)
async def accept(request_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> ColleaguesOut:
    c = await _incoming(session, request_id, principal)
    c.status, c.responded_at = COLLEAGUE_ACTIVE, datetime.now(UTC)
    await _event(session, "classroom.colleague.accepted", c, principal.user_id, c.requester_id)
    await session.commit()
    return await list_colleagues(principal, session)


@router.post("/requests/{request_id}/decline", response_model=ColleaguesOut)
async def decline(request_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> ColleaguesOut:
    await session.delete(await _incoming(session, request_id, principal))
    await session.commit()
    return await list_colleagues(principal, session)


@router.delete("/{user_id}", response_model=ColleaguesOut)
async def remove(user_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> ColleaguesOut:
    """Убрать из коллег или отозвать свою заявку. Доступ к общим классам и тестам закрывается (сделанное остаётся)."""
    c = await pair(session, principal.user_id, user_id, lock=True)
    if c is None:
        raise ApiError(404, "colleague_not_found", "Такого коллеги нет")
    was_active = c.status == COLLEAGUE_ACTIVE
    if was_active:  # общие классы в обе стороны — закрыть (сделанное остаётся)
        shares = (await session.execute(
            select(GroupShare).join(Group, Group.id == GroupShare.group_id).where(or_(
                (Group.teacher_id == principal.user_id) & (GroupShare.colleague_id == user_id),
                (Group.teacher_id == user_id) & (GroupShare.colleague_id == principal.user_id),
            )).with_for_update(of=GroupShare)
        )).scalars().all()
        for share in shares:
            await logic.unshare(session, share, principal.user_id)
    await session.delete(c)
    if was_active:
        await _event(session, "classroom.colleague.removed", c, principal.user_id, user_id)
    await session.commit()
    return await list_colleagues(principal, session)
