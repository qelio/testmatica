"""Отзывы и рейтинг (ТЗ, раздел 3): отзыв ученика, ответ педагога, спор — всё через модератора."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_MODERATOR, ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError
from testmatica_common.ids import uuid7

from .. import profiles
from ..deps import auth, classroom, db, outbox
from ..models import (
    APPROVED,
    DISPUTE_DISMISSED,
    DISPUTE_OPEN,
    DISPUTE_UPHELD,
    PENDING,
    REJECTED,
    REVIEW_REMOVED,
    Review,
    TutorProfile,
)
from ..schemas import DisputeIn, MyReview, RemoveIn, ReplyIn, ReviewIn, ReviewPublic, ReviewsPage, TutorReview

router = APIRouter(tags=["reviews"])
teacher = auth.require(ROLE_TEACHER)
moderator = auth.require(ROLE_MODERATOR)


async def is_student_of(tutor_id: UUID, student_id: UUID) -> bool:
    """Оставить отзыв может любой ученик, привязанный к педагогу (в том числе бывший)."""
    if tutor_id == student_id:
        return False
    try:
        await classroom.get("/internal/links", params={"teacher_id": str(tutor_id), "student_id": str(student_id)})
    except ApiError as e:
        if e.status == 404:
            return False
        raise
    return True


async def refresh_rating(session: AsyncSession, tutor_id: UUID) -> None:
    """Рейтинг — средняя оценка опубликованных отзывов (1–10), с одним знаком после запятой."""
    avg, count = (
        await session.execute(
            select(func.avg(Review.rating), func.count()).where(Review.tutor_id == tutor_id, Review.status == APPROVED)
        )
    ).one()
    profile = await session.get(TutorProfile, tutor_id, with_for_update=True)
    if profile is None:
        profile = TutorProfile(user_id=tutor_id, subjects=[], subject_ids=[], levels=[], formats=[])
        session.add(profile)
    profile.rating = round(float(avg), 1) if count else None
    profile.reviews_count = count


def _reply(r: Review) -> str | None:
    return r.reply_text if r.reply_status == APPROVED else None


def _public(r: Review, names: dict[UUID, str]) -> ReviewPublic:
    return ReviewPublic(id=r.id, student_name=names.get(r.student_id, "Ученик"), rating=r.rating, text=r.text,
                        published_at=r.published_at or r.created_at, reply=_reply(r))


def _mine(r: Review, names: dict[UUID, str]) -> MyReview:
    return MyReview(id=r.id, tutor_id=r.tutor_id, tutor_name=names.get(r.tutor_id, "Педагог"), rating=r.rating, text=r.text,
                    status=r.status, comment=r.comment, reply=_reply(r), updated_at=r.updated_at)


def _for_tutor(r: Review, names: dict[UUID, str]) -> TutorReview:
    return TutorReview(**_public(r, names).model_dump(), reply_text=r.reply_text, reply_status=r.reply_status,
                       reply_comment=r.reply_comment, dispute_id=r.dispute_id, dispute_status=r.dispute_status,
                       dispute_comment=r.dispute_comment)


def event_data(r: Review, names: dict[UUID, str]) -> dict:
    return {"review_id": str(r.id), "tutor_id": str(r.tutor_id), "student_id": str(r.student_id),
            "tutor_name": names.get(r.tutor_id, "Педагог"), "student_name": names.get(r.student_id, "Ученик"),
            "rating": r.rating}


@router.get("/tutors/{tutor_id}/reviews", response_model=ReviewsPage)
async def tutor_reviews(
    tutor_id: UUID,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    principal: Principal | None = Depends(auth.optional),
    session: AsyncSession = Depends(db.session),
) -> ReviewsPage:
    """Опубликованные отзывы — всем, в том числе без входа; ученику педагога — ещё его отзыв и можно ли оставить."""
    published = (Review.tutor_id == tutor_id, Review.status == APPROVED)
    rows = list((await session.execute(
        select(Review).where(*published).order_by(Review.published_at.desc()).limit(limit).offset(offset)
    )).scalars())
    distribution = dict((await session.execute(
        select(Review.rating, func.count()).where(*published).group_by(Review.rating)
    )).all())
    profile = await session.get(TutorProfile, tutor_id)
    mine, can_review = None, False
    if principal is not None and principal.user_id != tutor_id:
        mine = await session.scalar(select(Review).where(Review.tutor_id == tutor_id, Review.student_id == principal.user_id))
        can_review = await is_student_of(tutor_id, principal.user_id)
    names = await profiles.names(session, [r.student_id for r in rows] + [tutor_id])
    total = sum(distribution.values())
    return ReviewsPage(
        items=[_public(r, names) for r in rows], total=total, rating=profile.rating if profile else None,
        reviews_count=profile.reviews_count if profile else 0, distribution={n: distribution.get(n, 0) for n in range(1, 11)},
        can_review=can_review, mine=_mine(mine, names) if mine else None,
    )


@router.put("/tutors/{tutor_id}/review", response_model=MyReview)
async def save_review(
    tutor_id: UUID, body: ReviewIn, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> MyReview:
    """Оставить или изменить свой отзыв. Изменённый отзыв снова проверяет модератор и до этого не показывается."""
    if not await is_student_of(tutor_id, principal.user_id):
        raise ApiError(403, "not_student", "Отзыв может оставить только ученик этого педагога")
    r = await session.scalar(
        select(Review).where(Review.tutor_id == tutor_id, Review.student_id == principal.user_id).with_for_update()
    )
    now = datetime.now(UTC)
    if r is None:
        r = Review(tutor_id=tutor_id, student_id=principal.user_id)
        session.add(r)
    elif r.status == REVIEW_REMOVED:
        raise ApiError(409, "review_removed", "Отзыв удалён модератором — изменить его нельзя")
    elif r.rating == body.rating and r.text == body.text:
        return _mine(r, await profiles.names(session, [tutor_id]))
    was_published = r.status == APPROVED
    r.rating, r.text, r.status, r.comment, r.updated_at = body.rating, body.text, PENDING, None, now
    # Старый ответ педагога относился к прежнему тексту — снимаем; спор по старой версии теряет смысл.
    r.reply_text = r.reply_status = r.reply_comment = r.reply_at = None
    if r.dispute_status == DISPUTE_OPEN:
        r.dispute_status, r.dispute_comment = DISPUTE_DISMISSED, "Ученик изменил отзыв"
    await session.flush()
    if was_published:
        await refresh_rating(session, tutor_id)
    names = await profiles.names(session, [tutor_id, principal.user_id])
    await outbox.event(session, "marketplace.review.submitted", event_data(r, names) | {"text": r.text},
                       actor_id=principal.user_id)
    await session.commit()
    return _mine(r, names)


@router.get("/reviews/mine", response_model=list[MyReview])
async def my_reviews(principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> list[MyReview]:
    rows = list((await session.execute(
        select(Review).where(Review.student_id == principal.user_id).order_by(Review.updated_at.desc())
    )).scalars())
    names = await profiles.names(session, [r.tutor_id for r in rows])
    return [_mine(r, names) for r in rows]


@router.delete("/reviews/{review_id}", status_code=204)
async def delete_review(review_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> None:
    """Автор может удалить свой отзыв."""
    r = await session.get(Review, review_id, with_for_update=True)
    if r is None or r.student_id != principal.user_id:
        raise ApiError(404, "review_not_found", "Отзыв не найден")
    await session.delete(r)
    await session.flush()
    await refresh_rating(session, r.tutor_id)
    await outbox.event(session, "marketplace.review.withdrawn", {"review_id": str(r.id), "tutor_id": str(r.tutor_id)},
                       actor_id=principal.user_id)
    await session.commit()


# ---------- педагог: ответ и спор ----------


async def _tutor_review(session: AsyncSession, review_id: UUID, principal: Principal) -> Review:
    r = await session.get(Review, review_id, with_for_update=True)
    if r is None or r.tutor_id != principal.user_id or r.status != APPROVED:
        raise ApiError(404, "review_not_found", "Отзыв не найден")
    return r


@router.get("/me/reviews", response_model=list[TutorReview])
async def reviews_about_me(principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> list[TutorReview]:
    """Опубликованные отзывы о педагоге — с ответами и спорами. Отзывы на проверке педагогу не показываются."""
    rows = list((await session.execute(
        select(Review).where(Review.tutor_id == principal.user_id, Review.status == APPROVED).order_by(Review.published_at.desc())
    )).scalars())
    names = await profiles.names(session, [r.student_id for r in rows])
    return [_for_tutor(r, names) for r in rows]


@router.put("/reviews/{review_id}/reply", response_model=TutorReview)
async def reply(
    review_id: UUID, body: ReplyIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> TutorReview:
    """Публичный ответ на отзыв — появится после проверки модератором. Пустой текст убирает ответ."""
    r = await _tutor_review(session, review_id, principal)
    text = body.text.strip()
    names = await profiles.names(session, [r.tutor_id, r.student_id])
    if not text:
        r.reply_text = r.reply_status = r.reply_comment = r.reply_at = None
        await outbox.event(session, "marketplace.review.reply_withdrawn", {"review_id": str(r.id)}, actor_id=principal.user_id)
    elif text != r.reply_text or r.reply_status == REJECTED:
        r.reply_text, r.reply_status, r.reply_comment, r.reply_at = text, PENDING, None, datetime.now(UTC)
        await outbox.event(session, "marketplace.review.reply_submitted", event_data(r, names) | {"text": text, "review_text": r.text},
                           actor_id=principal.user_id)
    await session.commit()
    return _for_tutor(r, names)


@router.post("/reviews/{review_id}/dispute", response_model=TutorReview)
async def dispute(
    review_id: UUID, body: DisputeIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> TutorReview:
    """Оспорить отзыв: модератор получает заявку, а педагог — чат с модераторами (раздел «Поддержка»)."""
    r = await _tutor_review(session, review_id, principal)
    if r.dispute_status is not None:
        raise ApiError(409, "already_disputed", "Этот отзыв уже оспаривали" if r.dispute_status != DISPUTE_OPEN
                       else "Спор по отзыву уже открыт")
    r.dispute_id, r.dispute_reason, r.dispute_status, r.dispute_comment = uuid7(), body.reason.strip(), DISPUTE_OPEN, None
    names = await profiles.names(session, [r.tutor_id, r.student_id])
    # Текст спора и отзыва нужен модератору и чату; аудит видит его как обычное событие отзыва.
    await outbox.event(session, "marketplace.review.disputed",
                       event_data(r, names) | {"dispute_id": str(r.dispute_id), "reason": r.dispute_reason, "text": r.text},
                       actor_id=principal.user_id)
    await session.commit()
    return _for_tutor(r, names)


# ---------- модератор ----------


@router.delete("/moderation/reviews/{review_id}", status_code=204)
async def remove_review(
    review_id: UUID, body: RemoveIn, principal: Principal = Depends(moderator), session: AsyncSession = Depends(db.session)
) -> None:
    """Модератор снимает опубликованный отзыв (ТЗ: «Модерация, удаление»)."""
    r = await session.get(Review, review_id, with_for_update=True)
    if r is None:
        raise ApiError(404, "review_not_found", "Отзыв не найден")
    names = await profiles.names(session, [r.tutor_id, r.student_id])
    await remove(session, r, body.reason.strip(), names, principal.user_id)
    await session.commit()


async def remove(session: AsyncSession, r: Review, reason: str, names: dict[UUID, str], moderator_id: UUID | None) -> None:
    was_published = r.status == APPROVED
    r.status, r.comment, r.updated_at = REVIEW_REMOVED, reason, datetime.now(UTC)
    if r.dispute_status == DISPUTE_OPEN:
        r.dispute_status, r.dispute_comment = DISPUTE_UPHELD, reason
    await session.flush()
    if was_published:
        await refresh_rating(session, r.tutor_id)
    await outbox.event(session, "marketplace.review.removed", event_data(r, names) | {"comment": reason}, actor_id=moderator_id)
