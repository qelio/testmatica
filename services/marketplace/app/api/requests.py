"""Заявки учеников, отклики репетиторов и переговоры до «Договорились» (ТЗ, раздел 4)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import profiles
from ..deps import auth, db, outbox
from ..models import (
    REQUEST_AGREED,
    REQUEST_CLOSED,
    REQUEST_EXPIRED,
    REQUEST_OPEN,
    RESPONSE_ACTIVE,
    RESPONSE_AGREED,
    RESPONSE_CLOSED,
    Competency,
    LessonRequest,
    Response,
    TutorProfile,
)
from ..schemas import Negotiation, PersonBrief, PriceIn, RequestIn, RequestOut, RespondIn, ResponseOut

router = APIRouter(tags=["requests"])
teacher = auth.require(ROLE_TEACHER)

REQUEST_TTL = timedelta(days=14)  # решение №13
MAX_OPEN_PER_STUDENT = 5


# ---------- сборка ответов ----------


async def briefs(session: AsyncSession, ids: set[UUID]) -> dict[UUID, PersonBrief]:
    names = await profiles.names(session, ids)
    rows = (await session.execute(select(TutorProfile).where(TutorProfile.user_id.in_(ids)))).scalars().all() if ids else []
    photos = await profiles.photo_urls([p.photo_file_id for p in rows if p.photo_file_id])
    by_id = {p.user_id: p for p in rows}
    out = {}
    for uid in ids:
        p = by_id.get(uid)
        out[uid] = PersonBrief(
            id=uid, full_name=names.get(uid, "Пользователь"),
            photo_url=photos.get(str(p.photo_file_id)) if p and p.photo_file_id else None,
            rating=p.rating if p else None, reviews_count=p.reviews_count if p else 0,
        )
    return out


def _response_out(r: Response, people: dict[UUID, PersonBrief]) -> ResponseOut:
    return ResponseOut(id=r.id, request_id=r.request_id, tutor=people[r.tutor_id], status=r.status, price=r.price,
                       proposed_by=r.proposed_by, message=r.message, agreed_at=r.agreed_at, created_at=r.created_at)


async def _requests_out(session: AsyncSession, requests: list[LessonRequest], viewer: UUID) -> list[RequestOut]:
    if not requests:
        return []
    responses = (await session.execute(
        select(Response).where(Response.request_id.in_([r.id for r in requests])).order_by(Response.created_at)
    )).scalars().all()
    comp_ids = {c for r in requests for c in [*r.current_ids, *r.desired_ids]}
    titles = dict((await session.execute(select(Competency.id, Competency.title).where(Competency.id.in_(comp_ids)))).all()) if comp_ids else {}
    people = await briefs(session, {r.student_id for r in requests} | {x.tutor_id for x in responses})
    out = []
    for req in requests:
        mine = [x for x in responses if x.request_id == req.id and (req.student_id == viewer or x.tutor_id == viewer)]
        out.append(RequestOut(
            id=req.id, student=people[req.student_id], tutor_id=req.tutor_id, direct=req.tutor_id is not None,
            subject_id=req.subject_id, subject_name=req.subject_name, goal=req.goal,
            current=[titles[c] for c in req.current_ids if c in titles], desired=[titles[c] for c in req.desired_ids if c in titles],
            schedule=req.schedule, price=req.price, duration_min=req.duration_min, comment=req.comment, status=req.status,
            expires_at=req.expires_at, closed_at=req.closed_at, created_at=req.created_at,
            responses=[_response_out(x, people) for x in mine],
        ))
    return out


def _deal_data(req: LessonRequest, r: Response) -> dict:
    return {"response_id": str(r.id), "request_id": str(req.id), "student_id": str(req.student_id), "tutor_id": str(r.tutor_id),
            "subject": req.subject_name, "price": r.price, "duration_min": req.duration_min, "direct": req.tutor_id is not None}


async def _open_response(session: AsyncSession, req: LessonRequest, tutor_id: UUID, price: int, proposed_by: str,
                         message: str, actor: UUID) -> Response:
    r = Response(request_id=req.id, tutor_id=tutor_id, price=price, proposed_by=proposed_by, message=message.strip())
    session.add(r)
    await session.flush()
    # chat создаёт по этому событию чат переговоров с id отклика.
    await outbox.event(session, "marketplace.response.created", _deal_data(req, r) | {"message": r.message}, actor_id=actor)
    return r


async def _close_responses(session: AsyncSession, req: LessonRequest, reason: str, actor: UUID | None, keep: UUID | None = None) -> None:
    rows = (await session.execute(
        select(Response).where(Response.request_id == req.id, Response.status == RESPONSE_ACTIVE).with_for_update()
    )).scalars().all()
    for r in rows:
        if r.id == keep:
            continue
        r.status = RESPONSE_CLOSED
        await outbox.event(session, "marketplace.response.closed", _deal_data(req, r) | {"reason": reason}, actor_id=actor)


# ---------- ученик ----------


@router.post("/requests", response_model=RequestOut, status_code=201)
async def create_request(body: RequestIn, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> RequestOut:
    """Заявка ученика. Адресная сразу открывает переговоры с репетитором; открытую видят все репетиторы предмета."""
    known = await profiles.subjects()
    if str(body.subject_id) not in known:
        raise ApiError(422, "unknown_subject", "Такого предмета нет в справочнике")
    comp_ids = set(body.current_ids) | set(body.desired_ids)
    if comp_ids:
        valid = set((await session.execute(
            select(Competency.id).where(Competency.id.in_(comp_ids), Competency.subject_id == body.subject_id)
        )).scalars())
        if valid != comp_ids:
            raise ApiError(422, "unknown_competency", "Компетенции должны относиться к выбранному предмету")
    if body.tutor_id:
        if body.tutor_id == principal.user_id:
            raise ApiError(422, "self_request", "Нельзя оставить заявку самому себе")
        tutor = await session.get(TutorProfile, body.tutor_id)
        if tutor is None or not tutor.published:
            raise ApiError(404, "tutor_not_found", "Репетитор не найден")
    opened = await session.scalar(select(func.count()).select_from(LessonRequest).where(
        LessonRequest.student_id == principal.user_id, LessonRequest.status == REQUEST_OPEN))
    if opened >= MAX_OPEN_PER_STUDENT:
        raise ApiError(409, "too_many_requests", f"Открытых заявок может быть не больше {MAX_OPEN_PER_STUDENT} — закройте ненужные")

    now = datetime.now(UTC)
    req = LessonRequest(
        student_id=principal.user_id, tutor_id=body.tutor_id, subject_id=body.subject_id, subject_name=known[str(body.subject_id)],
        goal=body.goal, current_ids=list(dict.fromkeys(body.current_ids)), desired_ids=list(dict.fromkeys(body.desired_ids)),
        schedule=body.schedule.model_dump(), price=body.price, duration_min=body.duration_min, comment=body.comment.strip(),
        status=REQUEST_OPEN, expires_at=now + REQUEST_TTL,
    )
    session.add(req)
    await session.flush()
    response_id = None
    if body.tutor_id:
        tutor_ids = [body.tutor_id]
        response_id = (await _open_response(session, req, body.tutor_id, req.price, "student", req.comment, principal.user_id)).id
    else:
        # Уведомить репетиторов предмета, которые показываются в поиске (ТЗ: «всем репетиторам по этому предмету»).
        tutor_ids = list((await session.execute(
            select(TutorProfile.user_id).where(TutorProfile.published.is_(True), TutorProfile.subject_ids.contains([req.subject_id]),
                                               TutorProfile.user_id != principal.user_id).limit(1000)
        )).scalars())
    await outbox.event(session, "marketplace.request.created", {
        "request_id": str(req.id), "student_id": str(req.student_id), "subject": req.subject_name, "direct": body.tutor_id is not None,
        "tutor_ids": [str(t) for t in tutor_ids], "price": req.price, "duration_min": req.duration_min,
        "response_id": str(response_id) if response_id else None,
    }, actor_id=principal.user_id)
    await session.commit()
    return (await _requests_out(session, [req], principal.user_id))[0]


@router.get("/requests/mine", response_model=list[RequestOut])
async def my_requests(principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> list[RequestOut]:
    rows = (await session.execute(
        select(LessonRequest).where(LessonRequest.student_id == principal.user_id).order_by(LessonRequest.created_at.desc()).limit(50)
    )).scalars().all()
    return await _requests_out(session, list(rows), principal.user_id)


@router.post("/requests/{request_id}/close", response_model=RequestOut)
async def close_request(request_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> RequestOut:
    """Ученик закрывает заявку сам — переговоры по ней закрываются."""
    req = await session.get(LessonRequest, request_id, with_for_update=True)
    if req is None or req.student_id != principal.user_id:
        raise ApiError(404, "request_not_found", "Заявка не найдена")
    if req.status != REQUEST_OPEN:
        raise ApiError(409, "request_not_open", "Заявка уже закрыта")
    req.status, req.closed_at = REQUEST_CLOSED, datetime.now(UTC)
    await _close_responses(session, req, "student_closed", principal.user_id)
    await session.commit()
    return (await _requests_out(session, [req], principal.user_id))[0]


# ---------- репетитор ----------


@router.get("/requests/open", response_model=list[RequestOut])
async def open_requests(
    subject_id: UUID | None = None,
    all_subjects: bool = Query(False, description="Все предметы, а не только из профиля"),
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> list[RequestOut]:
    """Открытые заявки для репетитора — по умолчанию по предметам из его профиля."""
    query = select(LessonRequest).where(LessonRequest.status == REQUEST_OPEN, LessonRequest.tutor_id.is_(None),
                                        LessonRequest.student_id != principal.user_id)
    if subject_id:
        query = query.where(LessonRequest.subject_id == subject_id)
    elif not all_subjects:
        profile = await session.get(TutorProfile, principal.user_id)
        query = query.where(LessonRequest.subject_id.in_(profile.subject_ids if profile and profile.subject_ids else []))
    rows = (await session.execute(query.order_by(LessonRequest.created_at.desc()).limit(100))).scalars().all()
    return await _requests_out(session, list(rows), principal.user_id)


@router.post("/requests/{request_id}/respond", response_model=Negotiation, status_code=201)
async def respond(
    request_id: UUID, body: RespondIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> Negotiation:
    """Откликнуться на открытую заявку: открывается чат переговоров с учеником."""
    req = await session.get(LessonRequest, request_id, with_for_update=True)
    if req is None or req.tutor_id is not None or req.student_id == principal.user_id:
        raise ApiError(404, "request_not_found", "Заявка не найдена")
    if req.status != REQUEST_OPEN:
        raise ApiError(409, "request_not_open", "Заявка уже закрыта")
    profile = await session.get(TutorProfile, principal.user_id)
    if profile is None or not profile.published:
        raise ApiError(409, "profile_not_published", "Чтобы откликаться, включите показ профиля в поиске")
    existing = await session.scalar(select(Response).where(Response.request_id == req.id, Response.tutor_id == principal.user_id))
    if existing:
        raise ApiError(409, "already_responded", "Вы уже откликнулись на эту заявку")
    price = body.price or req.price
    r = await _open_response(session, req, principal.user_id, price, "tutor" if price != req.price else "student",
                             body.message, principal.user_id)
    await session.commit()
    return await _negotiation(session, r, principal)


@router.get("/responses/mine", response_model=list[RequestOut])
async def my_responses(principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> list[RequestOut]:
    """Переговоры репетитора: адресные заявки ему и его отклики на открытые."""
    ids = (await session.execute(
        select(Response.request_id).where(Response.tutor_id == principal.user_id).order_by(Response.created_at.desc()).limit(100)
    )).scalars().all()
    if not ids:
        return []
    rows = (await session.execute(select(LessonRequest).where(LessonRequest.id.in_(ids)))).scalars().all()
    order = {rid: i for i, rid in enumerate(ids)}
    return await _requests_out(session, sorted(rows, key=lambda r: order[r.id]), principal.user_id)


# ---------- переговоры ----------


async def _load(session: AsyncSession, response_id: UUID, p: Principal, lock: bool = False) -> tuple[Response, LessonRequest, str]:
    r = await session.get(Response, response_id, with_for_update=lock)
    if r is not None:
        req = await session.get(LessonRequest, r.request_id, with_for_update=lock)
        if r.tutor_id == p.user_id:
            return r, req, "tutor"
        if req.student_id == p.user_id:
            return r, req, "student"
    raise ApiError(404, "response_not_found", "Переговоры не найдены")


async def _negotiation(session: AsyncSession, r: Response, p: Principal) -> Negotiation:
    r, req, role = await _load(session, r.id, p)
    [request] = await _requests_out(session, [req], p.user_id)
    response = next(x for x in request.responses if x.id == r.id)
    return Negotiation(response=response, request=request, role=role,
                       can_agree=r.status == RESPONSE_ACTIVE and req.status == REQUEST_OPEN and r.proposed_by != role)


@router.get("/responses/{response_id}", response_model=Negotiation)
async def get_negotiation(response_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> Negotiation:
    r, _, _ = await _load(session, response_id, principal)
    return await _negotiation(session, r, principal)


def _active(r: Response, req: LessonRequest) -> None:
    if r.status != RESPONSE_ACTIVE or req.status != REQUEST_OPEN:
        raise ApiError(409, "negotiation_closed", "Переговоры завершены")


@router.post("/responses/{response_id}/price", response_model=Negotiation)
async def propose_price(
    response_id: UUID, body: PriceIn, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> Negotiation:
    """Предложить цену. Договориться можно о цене, предложенной другой стороной."""
    r, req, role = await _load(session, response_id, principal, lock=True)
    _active(r, req)
    r.price, r.proposed_by = body.price, role
    await outbox.event(session, "marketplace.response.price_proposed", _deal_data(req, r) | {"by": role}, actor_id=principal.user_id)
    await session.commit()
    return await _negotiation(session, r, principal)


@router.post("/responses/{response_id}/agree", response_model=Negotiation)
async def agree(response_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> Negotiation:
    """«Договорились»: цена фиксируется, заявка закрывается, остальные отклики — тоже (с уведомлением)."""
    r, req, role = await _load(session, response_id, principal, lock=True)
    _active(r, req)
    if r.proposed_by == role:
        raise ApiError(409, "own_proposal", "Эту цену предложили вы — дождитесь ответа или предложите другую")
    now = datetime.now(UTC)
    r.status, r.agreed_at = RESPONSE_AGREED, now
    req.status, req.closed_at = REQUEST_AGREED, now
    await _close_responses(session, req, "agreed_other", principal.user_id, keep=r.id)
    # classroom привяжет ученика к репетитору (платные индивидуальные занятия по этой цене), chat и notification — сообщат.
    await outbox.event(session, "marketplace.deal.agreed", _deal_data(req, r), actor_id=principal.user_id)
    await session.commit()
    return await _negotiation(session, r, principal)


@router.post("/responses/{response_id}/decline", response_model=Negotiation)
async def decline(response_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> Negotiation:
    """Отказаться от переговоров: репетитор — «не смогу», ученик — «не подходит». Адресная заявка закрывается."""
    r, req, role = await _load(session, response_id, principal, lock=True)
    _active(r, req)
    r.status = RESPONSE_CLOSED
    await outbox.event(session, "marketplace.response.closed", _deal_data(req, r) | {"reason": f"declined_by_{role}"},
                       actor_id=principal.user_id)
    if req.tutor_id is not None:
        req.status, req.closed_at = REQUEST_CLOSED, datetime.now(UTC)
    await session.commit()
    return await _negotiation(session, r, principal)


async def expire_requests() -> None:
    """Фоновая задача: открытые заявки закрываются через 14 дней (решение №13)."""
    now = datetime.now(UTC)
    async with db.sessionmaker() as session, session.begin():
        rows = (await session.execute(
            select(LessonRequest).where(LessonRequest.status == REQUEST_OPEN, LessonRequest.expires_at < now)
            .with_for_update(skip_locked=True).limit(200)
        )).scalars().all()
        for req in rows:
            req.status, req.closed_at = REQUEST_EXPIRED, now
            await _close_responses(session, req, "expired", None)
            await outbox.event(session, "marketplace.request.expired", {"request_id": str(req.id), "student_id": str(req.student_id),
                                                                         "subject": req.subject_name})
