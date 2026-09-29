"""События identity (имена) и moderation (решения по документам об образовании и отзывам)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .deps import outbox
from .api import reviews
from .models import (
    APPROVED,
    DISPUTE_DISMISSED,
    DISPUTE_OPEN,
    PENDING,
    REJECTED,
    EducationDoc,
    Person,
    Review,
    TutorProfile,
)
from .profiles import names


async def on_identity_event(envelope: Envelope, session: AsyncSession) -> None:
    if envelope.type in ("identity.user.registered", "identity.user.snapshot", "identity.user.updated"):
        d = envelope.data
        values = {"user_id": UUID(d["user_id"]), "full_name": d["full_name"]}
        update = {"full_name": d["full_name"]}
        if d.get("roles") is not None:
            values["roles"] = update["roles"] = d["roles"]
        if "avatar_file_id" in d:
            values["avatar_file_id"] = update["avatar_file_id"] = _uuid(d["avatar_file_id"])
        await session.execute(insert(Person).values(**values).on_conflict_do_update(index_elements=["user_id"], set_=update))
        if "avatar_file_id" in d:
            await _sync_photo(session, UUID(d["user_id"]), _uuid(d["avatar_file_id"]))
    elif envelope.type == "identity.user.avatar_changed":
        user_id, file_id = UUID(envelope.data["user_id"]), _uuid(envelope.data.get("file_id"))
        person = await session.get(Person, user_id, with_for_update=True)
        if person is not None:
            person.avatar_file_id = file_id
        await _sync_photo(session, user_id, file_id)


def _uuid(value: str | None) -> UUID | None:
    return UUID(value) if value else None


async def _sync_photo(session: AsyncSession, user_id: UUID, file_id: UUID | None) -> None:
    """Фото в анкете репетитора — то же, что в личном кабинете (хранит identity)."""
    profile = await session.get(TutorProfile, user_id, with_for_update=True)
    if profile is not None:
        profile.photo_file_id = file_id


async def on_moderation_decision(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    if d.get("kind") in ("review", "review_reply", "review_dispute"):
        await _review_decision(d, session)
        return
    if d.get("kind") != "education_doc":
        return
    doc = await session.get(EducationDoc, UUID(d["ref_id"]), with_for_update=True)
    if doc is None or doc.status != PENDING:
        return
    approved = d["decision"] == "approve"
    doc.status, doc.comment, doc.decided_at = (APPROVED if approved else REJECTED), d.get("comment"), datetime.now(UTC)
    profile = await session.get(TutorProfile, doc.user_id, with_for_update=True)
    if profile is not None and approved:
        profile.education_verified = True
    await outbox.event(
        session, "marketplace.education.approved" if approved else "marketplace.education.rejected",
        {"doc_id": str(doc.id), "user_id": str(doc.user_id), "title": doc.title, "comment": doc.comment},
        actor_id=UUID(d["moderator_id"]) if d.get("moderator_id") else None,
    )


async def _review_decision(d: dict, session: AsyncSession) -> None:
    """Решения модератора по отзыву, ответу педагога и спору."""
    r = await session.get(Review, UUID(d["ref_id"]), with_for_update=True)
    if r is None:
        return  # автор успел удалить отзыв
    approved = d["decision"] == "approve"
    comment = d.get("comment")
    moderator = UUID(d["moderator_id"]) if d.get("moderator_id") else None
    now = datetime.now(UTC)
    people = await names(session, [r.tutor_id, r.student_id])
    data = reviews.event_data(r, people) | {"comment": comment}
    kind = d["kind"]
    if kind == "review":
        if r.status != PENDING:
            return
        r.status, r.comment = (APPROVED if approved else REJECTED), comment
        if approved:
            r.published_at = now
        await session.flush()
        await reviews.refresh_rating(session, r.tutor_id)
        await outbox.event(session, "marketplace.review.approved" if approved else "marketplace.review.rejected", data,
                           actor_id=moderator)
    elif kind == "review_reply":
        if r.reply_status != PENDING:
            return
        r.reply_status, r.reply_comment = (APPROVED if approved else REJECTED), comment
        await outbox.event(session, "marketplace.review.reply_approved" if approved else "marketplace.review.reply_rejected",
                           data, actor_id=moderator)
    elif kind == "review_dispute":
        if r.dispute_status != DISPUTE_OPEN:
            return
        dispute = {"dispute_id": str(r.dispute_id), "upheld": approved}
        if approved:  # спор педагога признан — отзыв снимается
            await reviews.remove(session, r, comment or "Удалён по спору педагога", people, moderator)
        else:
            r.dispute_status, r.dispute_comment = DISPUTE_DISMISSED, comment
        await outbox.event(session, "marketplace.review.dispute_resolved", data | dispute, actor_id=moderator)
