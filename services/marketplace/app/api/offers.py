"""Наборы в группы (ТЗ, раздел 4): карточка группы, запись учеников, запуск при минимуме, недобор."""

from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_ADMIN, ROLE_STUDENT, ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import profiles
from ..config import settings
from ..deps import auth, classroom, db, outbox
from ..models import (
    OFFER_CANCELLED,
    OFFER_CLOSED,
    OFFER_RECRUITING,
    OFFER_STARTED,
    OFFER_UNDERFILLED,
    GroupEnrollment,
    GroupOffer,
)
from ..schemas import ExtendIn, OfferIn, OfferOut, OfferSchedule, OfferStudent, SubjectRef
from .requests import briefs

router = APIRouter(tags=["offers"])
teacher = auth.require(ROLE_TEACHER)
student = auth.require(ROLE_STUDENT)

EDITABLE = (OFFER_RECRUITING, OFFER_UNDERFILLED)


def _today(offer: GroupOffer) -> date:
    """«Сегодня» в часовом поясе расписания группы — от него считается срок набора."""
    try:
        zone = ZoneInfo(offer.schedule.get("timezone") or "Europe/Moscow")
    except Exception:
        zone = ZoneInfo("Europe/Moscow")
    return datetime.now(zone).date()


def joinable(offer: GroupOffer, count: int) -> bool:
    if count >= offer.max_students:
        return False
    if offer.status == OFFER_RECRUITING:
        return _today(offer) <= offer.enroll_until
    return offer.status == OFFER_STARTED  # в идущую группу можно войти, пока есть места и набор не закрыт


async def _counts(session: AsyncSession, ids: list[UUID]) -> dict[UUID, int]:
    if not ids:
        return {}
    rows = await session.execute(
        select(GroupEnrollment.offer_id, func.count()).where(GroupEnrollment.offer_id.in_(ids)).group_by(GroupEnrollment.offer_id)
    )
    return dict(rows.all())


async def _out(session: AsyncSession, offers: list[GroupOffer], viewer: Principal | None) -> list[OfferOut]:
    ids = [o.id for o in offers]
    counts = await _counts(session, ids)
    tutors = await briefs(session, {o.tutor_id for o in offers})
    mine: set[UUID] = set()
    if viewer is not None and ids:
        mine = set((await session.execute(
            select(GroupEnrollment.offer_id).where(GroupEnrollment.offer_id.in_(ids), GroupEnrollment.student_id == viewer.user_id)
        )).scalars())
    owned = [o.id for o in offers if viewer is not None and o.tutor_id == viewer.user_id]
    students: dict[UUID, list[OfferStudent]] = {i: [] for i in owned}
    if owned:
        rows = (await session.execute(
            select(GroupEnrollment).where(GroupEnrollment.offer_id.in_(owned)).order_by(GroupEnrollment.created_at)
        )).scalars().all()
        names = await profiles.names(session, [r.student_id for r in rows])
        for r in rows:
            students[r.offer_id].append(OfferStudent(id=r.student_id, full_name=names.get(r.student_id, "Ученик"), enrolled_at=r.created_at))
    out = []
    for o in offers:
        count = counts.get(o.id, 0)
        out.append(OfferOut(
            id=o.id, tutor=tutors[o.tutor_id], title=o.title, subject=SubjectRef(id=o.subject_id, name=o.subject_name), levels=o.levels,
            description=o.description, program=o.program, schedule=OfferSchedule(**o.schedule), price=o.price,
            min_students=o.min_students, max_students=o.max_students, enroll_until=o.enroll_until, private=o.private,
            status=o.status, enrolled_count=count, seats_left=max(0, o.max_students - count), joinable=joinable(o, count),
            enrolled=o.id in mine, is_owner=o.id in students, share_url=f"{settings.web_base_url}/groups/{o.id}",
            students=students.get(o.id), started_at=o.started_at, created_at=o.created_at,
        ))
    return out


async def _one(session: AsyncSession, offer: GroupOffer, viewer: Principal | None) -> OfferOut:
    return (await _out(session, [offer], viewer))[0]


async def _get(session: AsyncSession, offer_id: UUID, lock: bool = False) -> GroupOffer:
    o = await session.get(GroupOffer, offer_id, with_for_update=lock)
    if o is None:
        raise ApiError(404, "offer_not_found", "Набор не найден")
    return o


async def _own(session: AsyncSession, offer_id: UUID, principal: Principal) -> GroupOffer:
    o = await _get(session, offer_id, lock=True)
    if o.tutor_id != principal.user_id:
        raise ApiError(404, "offer_not_found", "Набор не найден")
    return o


async def _student_ids(session: AsyncSession, offer_id: UUID) -> list[str]:
    rows = await session.execute(
        select(GroupEnrollment.student_id).where(GroupEnrollment.offer_id == offer_id).order_by(GroupEnrollment.created_at)
    )
    return [str(s) for s in rows.scalars()]


def _event(o: GroupOffer, **extra) -> dict:
    return {"offer_id": str(o.id), "tutor_id": str(o.tutor_id), "title": o.title, "subject": o.subject_name} | extra


async def _subject(subject_id: UUID) -> str:
    name = (await profiles.subjects()).get(str(subject_id))
    if name is None:
        raise ApiError(422, "unknown_subject", "Такого предмета нет в справочнике")
    return name


def _apply(o: GroupOffer, body: OfferIn, subject_name: str) -> None:
    o.title, o.subject_id, o.subject_name, o.levels = body.title, body.subject_id, subject_name, list(dict.fromkeys(body.levels))
    o.description, o.program, o.schedule = body.description.strip(), body.program, body.schedule.model_dump(mode="json")
    o.price, o.min_students, o.max_students = body.price, body.min_students, body.max_students
    o.enroll_until, o.private = body.enroll_until, body.private


# ---------- каталог и просмотр ----------


@router.get("/offers", response_model=list[OfferOut])
async def catalog(
    subject_id: UUID | None = None,
    level: str | None = Query(None, pattern="^(1-4|5-9|10-11|student|adult)$"),
    price_max: int | None = Query(None, ge=0),
    limit: int = Query(30, ge=1, le=60),
    offset: int = Query(0, ge=0),
    principal: Principal | None = Depends(auth.optional),
    session: AsyncSession = Depends(db.session),
) -> list[OfferOut]:
    """Открытые наборы — видны всем, в том числе без входа. Закрытые сюда не попадают."""
    query = select(GroupOffer).where(GroupOffer.private.is_(False), GroupOffer.status.in_((OFFER_RECRUITING, OFFER_STARTED)))
    if subject_id:
        query = query.where(GroupOffer.subject_id == subject_id)
    if level:
        query = query.where(GroupOffer.levels.contains([level]))
    if price_max is not None:
        query = query.where(GroupOffer.price <= price_max)
    rows = (await session.execute(query.order_by(GroupOffer.status.desc(), GroupOffer.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    # Идущие группы без свободных мест в каталоге не нужны.
    return [o for o in await _out(session, list(rows), principal) if o.joinable or o.status == OFFER_RECRUITING]


@router.get("/tutors/{tutor_id}/offers", response_model=list[OfferOut])
async def tutor_offers(
    tutor_id: UUID, principal: Principal | None = Depends(auth.optional), session: AsyncSession = Depends(db.session)
) -> list[OfferOut]:
    """Активные группы и наборы репетитора — для публичного профиля."""
    rows = (await session.execute(
        select(GroupOffer).where(GroupOffer.tutor_id == tutor_id, GroupOffer.private.is_(False),
                                 GroupOffer.status.in_((OFFER_RECRUITING, OFFER_STARTED, OFFER_CLOSED)))
        .order_by(GroupOffer.created_at.desc())
    )).scalars().all()
    return await _out(session, list(rows), principal)


@router.get("/offers/mine", response_model=list[OfferOut])
async def my_offers(principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> list[OfferOut]:
    rows = (await session.execute(
        select(GroupOffer).where(GroupOffer.tutor_id == principal.user_id).order_by(GroupOffer.created_at.desc())
    )).scalars().all()
    return await _out(session, list(rows), principal)


@router.get("/offers/enrolled", response_model=list[OfferOut])
async def enrolled(principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> list[OfferOut]:
    rows = (await session.execute(
        select(GroupOffer).join(GroupEnrollment, GroupEnrollment.offer_id == GroupOffer.id)
        .where(GroupEnrollment.student_id == principal.user_id).order_by(GroupEnrollment.created_at.desc())
    )).scalars().all()
    return await _out(session, list(rows), principal)


@router.get("/offers/{offer_id}", response_model=OfferOut)
async def offer(offer_id: UUID, principal: Principal | None = Depends(auth.optional), session: AsyncSession = Depends(db.session)) -> OfferOut:
    """По ссылке открывается любой набор, в том числе закрытый."""
    return await _one(session, await _get(session, offer_id), principal)


# ---------- педагог ----------


@router.post("/offers", response_model=OfferOut, status_code=201)
async def create_offer(body: OfferIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> OfferOut:
    o = GroupOffer(tutor_id=principal.user_id, status=OFFER_RECRUITING)
    _apply(o, body, await _subject(body.subject_id))
    if o.enroll_until < _today(o):
        raise ApiError(422, "enroll_until_past", "Срок набора уже прошёл")
    session.add(o)
    await session.flush()
    await outbox.event(session, "marketplace.group_offer.created", _event(o, private=o.private), actor_id=principal.user_id)
    await session.commit()
    return await _one(session, o, principal)


@router.put("/offers/{offer_id}", response_model=OfferOut)
async def update_offer(
    offer_id: UUID, body: OfferIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> OfferOut:
    """Править можно до запуска группы. Максимум — не меньше уже записавшихся."""
    o = await _own(session, offer_id, principal)
    if o.status not in EDITABLE:
        raise ApiError(409, "offer_locked", "Группа уже запущена или набор отменён — карточку не изменить")
    count = (await _counts(session, [o.id])).get(o.id, 0)
    if body.max_students < count:
        raise ApiError(422, "too_many_enrolled", f"Уже записались {count} — максимум не может быть меньше")
    _apply(o, body, await _subject(body.subject_id))
    if o.status == OFFER_UNDERFILLED and o.enroll_until >= _today(o):
        o.status = OFFER_RECRUITING  # продлили срок набора
    await session.commit()
    return await _one(session, o, principal)


@router.post("/offers/{offer_id}/extend", response_model=OfferOut)
async def extend(offer_id: UUID, body: ExtendIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> OfferOut:
    """Продлить набор (ТЗ: «Педагог может продлить срок набора»); при необходимости сдвинуть первое занятие."""
    o = await _own(session, offer_id, principal)
    if o.status not in EDITABLE:
        raise ApiError(409, "offer_locked", "Продлить можно только идущий или недобранный набор")
    if body.enroll_until < _today(o):
        raise ApiError(422, "enroll_until_past", "Новый срок набора уже прошёл")
    start = body.start_date or date.fromisoformat(o.schedule["start_date"])
    if body.enroll_until > start:
        raise ApiError(422, "start_before_enroll_end", "Первое занятие — не раньше окончания набора; перенесите и его")
    o.enroll_until, o.schedule = body.enroll_until, o.schedule | {"start_date": start.isoformat()}
    o.status = OFFER_RECRUITING
    await outbox.event(session, "marketplace.group_offer.extended",
                       _event(o, enroll_until=o.enroll_until.isoformat(), student_ids=await _student_ids(session, o.id)),
                       actor_id=principal.user_id)
    await session.commit()
    return await _one(session, o, principal)


@router.post("/offers/{offer_id}/start", response_model=OfferOut)
async def start(offer_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> OfferOut:
    """Запустить группу, когда набрался минимум: classroom создаст группу с id набора и привяжет учеников."""
    o = await _own(session, offer_id, principal)
    if o.status not in EDITABLE:
        raise ApiError(409, "offer_locked", "Группа уже запущена или набор отменён")
    students = await _student_ids(session, o.id)
    if len(students) < o.min_students:
        raise ApiError(409, "not_enough_students", f"Записались {len(students)} из минимальных {o.min_students} — группа пока не может стартовать")
    limit = await classroom.get("/internal/group-limit", params={"teacher_id": str(principal.user_id)})
    if not limit["allowed"]:
        raise ApiError(403, "plan_limit", limit["message"])
    o.status, o.started_at = OFFER_STARTED, datetime.now(UTC)
    await outbox.event(session, "marketplace.group_offer.started",
                       _event(o, price=o.price, description=o.description, student_ids=students, schedule=o.schedule),
                       actor_id=principal.user_id)
    await session.commit()
    return await _one(session, o, principal)


@router.post("/offers/{offer_id}/cancel", response_model=OfferOut)
async def cancel(offer_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> OfferOut:
    """До запуска — отменить набор (записавшиеся получат уведомление). После — закрыть набор новых учеников."""
    o = await _own(session, offer_id, principal)
    if o.status in (OFFER_CANCELLED, OFFER_CLOSED):
        return await _one(session, o, principal)
    was_started = o.status == OFFER_STARTED
    o.status, o.closed_at = (OFFER_CLOSED if was_started else OFFER_CANCELLED), datetime.now(UTC)
    if not was_started:
        await outbox.event(session, "marketplace.group_offer.cancelled", _event(o, student_ids=await _student_ids(session, o.id)),
                           actor_id=principal.user_id)
    await session.commit()
    return await _one(session, o, principal)


# ---------- ученик ----------


@router.post("/offers/{offer_id}/join", response_model=OfferOut)
async def join(offer_id: UUID, principal: Principal = Depends(student), session: AsyncSession = Depends(db.session)) -> OfferOut:
    """Записаться — место резервируется. В идущую группу ученик попадает сразу (classroom добавит его)."""
    o = await _get(session, offer_id, lock=True)
    if o.tutor_id == principal.user_id:
        raise ApiError(409, "own_offer", "Это ваш набор")
    if await session.get(GroupEnrollment, (o.id, principal.user_id)) is not None:
        return await _one(session, o, principal)
    count = (await _counts(session, [o.id])).get(o.id, 0)
    if not joinable(o, count):
        if count >= o.max_students:
            raise ApiError(409, "offer_full", "Мест в группе нет")
        raise ApiError(409, "offer_closed", "Набор в эту группу закрыт")
    session.add(GroupEnrollment(offer_id=o.id, student_id=principal.user_id))
    await session.flush()
    count += 1
    name = (await profiles.names(session, [principal.user_id])).get(principal.user_id, "Ученик")
    await outbox.event(session, "marketplace.group_offer.joined",
                       _event(o, student_id=str(principal.user_id), student_name=name, count=count, min_students=o.min_students,
                              max_students=o.max_students, started=o.status == OFFER_STARTED),
                       actor_id=principal.user_id)
    if o.status == OFFER_RECRUITING and count >= o.min_students and o.min_reached_at is None:
        o.min_reached_at = datetime.now(UTC)
        await outbox.event(session, "marketplace.group_offer.min_reached", _event(o, count=count), actor_id=principal.user_id)
    await session.commit()
    return await _one(session, o, principal)


@router.post("/offers/{offer_id}/leave", response_model=OfferOut)
async def leave(offer_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> OfferOut:
    """Отменить запись можно до запуска группы; после — выйти из группы через педагога."""
    o = await _get(session, offer_id, lock=True)
    e = await session.get(GroupEnrollment, (o.id, principal.user_id))
    if e is None:
        return await _one(session, o, principal)
    if o.status not in EDITABLE:
        raise ApiError(409, "offer_started", "Группа уже занимается — чтобы выйти, напишите педагогу")
    await session.delete(e)
    await session.flush()
    await outbox.event(session, "marketplace.group_offer.left", _event(o, student_id=str(principal.user_id)), actor_id=principal.user_id)
    await session.commit()
    return await _one(session, o, principal)


# ---------- администратор ----------


class RemoveIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/admin/offers/{offer_id}/remove", response_model=OfferOut)
async def admin_remove(
    offer_id: UUID, body: RemoveIn, principal: Principal = Depends(auth.require(ROLE_ADMIN)), session: AsyncSession = Depends(db.session)
) -> OfferOut:
    """Снять набор с платформы: до запуска — отмена (записавшиеся получат уведомление), после — закрыть набор.
    Уже идущая группа в classroom остаётся — занятия продолжаются."""
    o = await _get(session, offer_id, lock=True)
    reason = body.reason.strip()
    if o.status in EDITABLE:
        o.status, o.closed_at = OFFER_CANCELLED, datetime.now(UTC)
        await outbox.event(session, "marketplace.group_offer.cancelled", _event(o, student_ids=await _student_ids(session, o.id)),
                           actor_id=principal.user_id)
    elif o.status == OFFER_STARTED:
        o.status, o.closed_at = OFFER_CLOSED, datetime.now(UTC)
    await outbox.event(session, "marketplace.group_offer.removed", _event(o, reason=reason), actor_id=principal.user_id)
    await session.commit()
    return await _one(session, o, principal)


# ---------- фоновая задача ----------


async def check_deadlines() -> None:
    """Срок набора прошёл, а минимум не набрался — «недобор»: педагог продлит набор или отменит его."""
    async with db.sessionmaker() as session, session.begin():
        rows = (await session.execute(
            select(GroupOffer).where(GroupOffer.status == OFFER_RECRUITING, GroupOffer.enroll_until < func.current_date())
            .with_for_update(skip_locked=True).limit(200)
        )).scalars().all()
        counts = await _counts(session, [o.id for o in rows])
        for o in rows:
            if o.enroll_until >= _today(o) or counts.get(o.id, 0) >= o.min_students:
                continue  # у кого набрался минимум — ждём запуска педагогом
            o.status = OFFER_UNDERFILLED
            await outbox.event(session, "marketplace.group_offer.underfilled",
                               _event(o, count=counts.get(o.id, 0), min_students=o.min_students,
                                      student_ids=await _student_ids(session, o.id)))


