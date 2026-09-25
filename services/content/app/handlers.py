"""Реакция на события identity, classroom и moderation."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .deps import outbox
from .models import PENDING, PUBLISHED, REJECTED, Node, Person, RelLink


async def on_identity_event(envelope: Envelope, session: AsyncSession) -> None:
    if envelope.type in ("identity.user.registered", "identity.user.snapshot", "identity.user.updated"):
        d = envelope.data
        await session.execute(
            insert(Person)
            .values(user_id=UUID(d["user_id"]), full_name=d["full_name"])
            .on_conflict_do_update(index_elements=["user_id"], set_={"full_name": d["full_name"]})
        )


async def on_classroom_event(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    if envelope.type in ("classroom.link.created", "classroom.link.snapshot"):
        await session.execute(
            insert(RelLink).values(teacher_id=UUID(d["teacher_id"]), student_id=UUID(d["student_id"])).on_conflict_do_nothing()
        )
    elif envelope.type == "classroom.link.ended":
        await session.execute(
            delete(RelLink).where(RelLink.teacher_id == UUID(d["teacher_id"]), RelLink.student_id == UUID(d["student_id"]))
        )


async def on_moderation_decision(envelope: Envelope, session: AsyncSession) -> None:
    """Решение модератора по курсу. Если автор успел отозвать курс — решение уже неактуально."""
    d = envelope.data
    if d.get("kind") != "course":
        return
    course = await session.get(Node, UUID(d["ref_id"]), with_for_update=True)
    if course is None or course.kind != "course" or course.status != PENDING:
        return
    approved = d["decision"] == "approve"
    course.status = PUBLISHED if approved else REJECTED
    course.review_comment = d.get("comment")
    if approved:
        course.published_at = datetime.now(UTC)
    await outbox.event(
        session,
        "content.course.published" if approved else "content.course.rejected",
        {
            "course_id": str(course.id),
            "title": course.title,
            "author_id": str(course.owner_id),
            "comment": d.get("comment"),
        },
        actor_id=UUID(d["moderator_id"]) if d.get("moderator_id") else None,
    )
