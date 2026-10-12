"""Реакция на события identity, classroom и moderation."""

from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from . import revisions
from .deps import outbox
from .models import PENDING, REJECTED, Node, Person, RelLink


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
    """Решение модератора по курсу. Если автор успел отозвать курс — решение уже неактуально.
    Черновик изменений опубликованного курса (решение №46): принят — переносится в опубликованную версию."""
    d = envelope.data
    if d.get("kind") != "course":
        return
    course = await session.get(Node, UUID(d["ref_id"]), with_for_update=True)
    if course is None or course.kind != "course" or course.status != PENDING:
        return
    approved = d["decision"] == "approve"
    revision_id = str(course.id) if course.revision_of else None
    course.review_comment = d.get("comment")
    if approved:
        course = await revisions.publish(session, course)
    else:
        course.status = REJECTED
    await outbox.event(
        session,
        "content.course.published" if approved else "content.course.rejected",
        {
            "course_id": str(course.id),
            "title": course.title,
            "author_id": str(course.owner_id),
            "comment": d.get("comment"),
            # Принятый или отклонённый черновик изменений: assessment по нему применяет или возвращает изменения тестов.
            "revision_id": revision_id,
            "revision_of": str(course.revision_of) if course.revision_of else (str(course.id) if revision_id else None),
        },
        actor_id=UUID(d["moderator_id"]) if d.get("moderator_id") else None,
    )
