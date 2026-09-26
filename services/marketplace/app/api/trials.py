"""После пробного занятия: ученику — предложение оставить отзыв и подтвердить продолжение (ТЗ, раздел 4)."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal
from testmatica_common.errors import ApiError
from testmatica_common.messaging import Envelope

from .. import profiles
from ..deps import auth, db, outbox
from ..models import TRIAL_PENDING, Review, TrialFollowup
from ..schemas import TrialAnswerIn, TrialOut
from .requests import briefs

router = APIRouter(tags=["trials"])


async def on_schedule_event(envelope: Envelope, session: AsyncSession) -> None:
    """Пробное занятие закончилось — по предложению каждому ученику (групповое пробное — тоже)."""
    if envelope.type != "schedule.lesson.trial_finished":
        return
    d = envelope.data
    tutor = UUID(d["teacher_id"])
    # В событии индивидуальное занятие подписано именем ученика (так его видит педагог) — ученику нужна своя подпись.
    name = "Индивидуальное занятие" if d.get("kind") == "individual" else d.get("title")
    title = " · ".join(x for x in (name, d.get("subject")) if x)
    for lesson_id in d["lesson_ids"]:
        for sid in d["student_ids"]:
            created = await session.execute(
                insert(TrialFollowup)
                .values(lesson_id=UUID(lesson_id), student_id=UUID(sid), tutor_id=tutor, title=title[:200],
                        lesson_starts_at=datetime.fromisoformat(d["starts_at"]), status=TRIAL_PENDING)
                .on_conflict_do_nothing()
                .returning(TrialFollowup.lesson_id)
            )
            if created.scalar() is not None:
                await outbox.event(session, "marketplace.trial.followup_created", {
                    "lesson_id": lesson_id, "student_id": sid, "tutor_id": str(tutor), "tutor_name": d.get("teacher_name"), "title": title})


async def _out(session: AsyncSession, rows: list[TrialFollowup], student_id: UUID) -> list[TrialOut]:
    tutors = await briefs(session, {r.tutor_id for r in rows})
    reviewed = set((await session.execute(
        select(Review.tutor_id).where(Review.student_id == student_id, Review.tutor_id.in_(list(tutors)))
    )).scalars()) if rows else set()
    return [TrialOut(lesson_id=r.lesson_id, tutor=tutors[r.tutor_id], title=r.title, lesson_starts_at=r.lesson_starts_at, status=r.status,
                     comment=r.comment, answered_at=r.answered_at, reviewed=r.tutor_id in reviewed) for r in rows]


@router.get("/trials/pending", response_model=list[TrialOut])
async def pending(principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> list[TrialOut]:
    """Пробные занятия, по которым ученик ещё не ответил, продолжает ли он."""
    rows = (await session.execute(
        select(TrialFollowup).where(TrialFollowup.student_id == principal.user_id, TrialFollowup.status == TRIAL_PENDING)
        .order_by(TrialFollowup.lesson_starts_at.desc())
    )).scalars().all()
    return await _out(session, list(rows), principal.user_id)


@router.post("/trials/{lesson_id}/answer", response_model=TrialOut)
async def answer(
    lesson_id: UUID, body: TrialAnswerIn, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> TrialOut:
    """Продолжаю / не продолжаю — педагог получит уведомление с комментарием."""
    f = await session.get(TrialFollowup, (lesson_id, principal.user_id), with_for_update=True)
    if f is None:
        raise ApiError(404, "trial_not_found", "Пробное занятие не найдено")
    if f.status != TRIAL_PENDING:
        raise ApiError(409, "trial_answered", "Вы уже ответили")
    f.status, f.comment, f.answered_at = body.decision, body.comment.strip(), datetime.now(UTC)
    name = (await profiles.names(session, [principal.user_id])).get(principal.user_id, "Ученик")
    await outbox.event(session, "marketplace.trial.answered", {
        "lesson_id": str(lesson_id), "student_id": str(principal.user_id), "student_name": name, "tutor_id": str(f.tutor_id),
        "decision": f.status, "comment": f.comment, "title": f.title}, actor_id=principal.user_id)
    await session.commit()
    return (await _out(session, [f], principal.user_id))[0]
