"""События identity, classroom, content и moderation."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .deps import outbox
from .models import PENDING, PRIVATE, PUBLISHED, REJECTED, CourseTask, Person, RelLink, Task


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


async def _publish(session: AsyncSession, task: Task, approved: bool, comment: str | None, actor: UUID | None) -> None:
    task.status = PUBLISHED if approved else REJECTED
    task.review_comment = comment
    if approved:
        task.published_at = datetime.now(UTC)
    await outbox.event(
        session,
        "assessment.task.published" if approved else "assessment.task.rejected",
        {"task_id": str(task.id), "title": task.title, "author_id": str(task.owner_id), "comment": comment},
        actor_id=actor,
    )


async def on_content_event(envelope: Envelope, session: AsyncSession) -> None:
    """Приватные задачи курса модерируются вместе с курсом и публикуются вместе с ним."""
    d = envelope.data
    course_id = UUID(d["course_id"])
    if envelope.type == "content.course.submitted":
        for tid in d.get("task_ids", []):
            task = await session.get(Task, UUID(tid), with_for_update=True)
            if task and task.owner_id == UUID(d["author_id"]) and task.status in (PRIVATE, REJECTED):
                task.status = PENDING
                await session.execute(insert(CourseTask).values(course_id=course_id, task_id=task.id).on_conflict_do_nothing())
        return
    bundle = (await session.execute(select(CourseTask.task_id).where(CourseTask.course_id == course_id))).scalars().all()
    for tid in bundle:
        task = await session.get(Task, tid, with_for_update=True)
        if task is None or task.status != PENDING:
            continue
        if envelope.type == "content.course.published":
            await _publish(session, task, True, None, envelope.actor_id)
        elif envelope.type == "content.course.rejected":
            await _publish(session, task, False, "Вернулась на доработку вместе с курсом", envelope.actor_id)
        elif envelope.type in ("content.course.unpublished", "content.course.deleted"):
            task.status = PRIVATE
    await session.execute(delete(CourseTask).where(CourseTask.course_id == course_id))


async def on_moderation_decision(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    if d.get("kind") != "task":
        return
    task = await session.get(Task, UUID(d["ref_id"]), with_for_update=True)
    if task is None or task.status != PENDING:
        return
    await _publish(session, task, d["decision"] == "approve", d.get("comment"),
                   UUID(d["moderator_id"]) if d.get("moderator_id") else None)
