"""События identity, classroom, content и moderation."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .courses import apply_pending, test_task_ids
from . import class_access
from .deps import outbox
from .models import IN_PROGRESS, PENDING, PRIVATE, PUBLISHED, REJECTED, Assignment, Attempt, CourseTask, Person, RelLink, Task, Test, TestShare


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
    elif envelope.type == "classroom.colleague.removed":
        # Убрали из коллег — закрыть доступ к тестам друг друга: и своим, и тем, которыми поделились (решение №58).
        a, b = UUID(d["requester_id"]), UUID(d["addressee_id"])
        for user, other in ((a, b), (b, a)):
            owned = select(Test.id).where(Test.owner_id == other)
            await session.execute(delete(TestShare).where(
                TestShare.user_id == user, or_(TestShare.shared_by == other, TestShare.test_id.in_(owned))
            ))


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
    """Задачи курса модерируются вместе с курсом и публикуются вместе с ним: задачи из материалов и из тестов автора
    к модулям курса — публичных и «для педагогов» (решение №46). Принят курс или его черновик изменений —
    тесты автора становятся видны другим, их предложенные изменения переносятся в сами тесты."""
    d = envelope.data
    course_id = UUID(d["course_id"])
    author = UUID(d["author_id"]) if d.get("author_id") else None
    if envelope.type == "content.course.tasks_added":
        # Штатный редактор добавил задачу в опубликованный курс — она публикуется сразу (решение №51).
        for tid in {UUID(x) for x in d.get("task_ids", [])}:
            task = await session.get(Task, tid, with_for_update=True)
            if task is not None and task.owner_id == author and task.status in (PRIVATE, REJECTED, PENDING):
                await _publish(session, task, True, None, envelope.actor_id)
        return
    live = UUID(d["revision_of"]) if d.get("revision_of") else course_id
    tests = (await session.execute(
        select(Test).where(Test.course_id == live, Test.owner_id == author).with_for_update()
    )).scalars().all() if author else []
    from_tests = {tid for t in tests for tid in test_task_ids(t)}
    if envelope.type == "content.course.submitted":
        for tid in {UUID(x) for x in d.get("task_ids", [])} | from_tests:
            task = await session.get(Task, tid, with_for_update=True)
            if task and task.owner_id == author and task.status in (PRIVATE, REJECTED):
                task.status = PENDING
                await session.execute(insert(CourseTask).values(course_id=course_id, task_id=task.id).on_conflict_do_nothing())
        return
    key = UUID(d["revision_id"]) if d.get("revision_id") else course_id  # проверялся черновик — задачи по нему
    bundle = set((await session.execute(select(CourseTask.task_id).where(CourseTask.course_id == key))).scalars())
    if envelope.type == "content.course.published":
        # Курсы штатных редакторов публикуются без проверки — их задачи публикуются сразу, без очереди.
        for tid in bundle | {UUID(x) for x in d.get("task_ids", [])} | from_tests:
            task = await session.get(Task, tid, with_for_update=True)
            if task is not None and task.owner_id == author and task.status in (PRIVATE, REJECTED, PENDING):
                await _publish(session, task, True, None, envelope.actor_id)
        now = datetime.now(UTC)
        for t in tests:
            apply_pending(t)
            t.published_at = t.published_at or now
    else:
        for tid in bundle:
            task = await session.get(Task, tid, with_for_update=True)
            if task is None or task.status != PENDING:
                continue
            if envelope.type == "content.course.rejected":
                await _publish(session, task, False, "Вернулась на доработку вместе с курсом", envelope.actor_id)
            elif envelope.type in ("content.course.unpublished", "content.course.deleted"):
                task.status = PRIVATE
    await session.execute(delete(CourseTask).where(CourseTask.course_id == key))


async def on_schedule_event(envelope: Envelope, session: AsyncSession) -> None:
    """Занятие удалили из расписания (решение №54) — ДЗ и тесты к нему остаются, привязка к уроку снимается."""
    if envelope.type != "schedule.lesson.deleted":
        return
    ids = [UUID(x) for x in envelope.data.get("lesson_ids", [])]
    if ids:
        await session.execute(update(Assignment).where(Assignment.lesson_id.in_(ids)).values(lesson_id=None))


async def on_moderation_decision(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    if d.get("kind") != "task":
        return
    task = await session.get(Task, UUID(d["ref_id"]), with_for_update=True)
    if task is None or task.status != PENDING:
        return
    await _publish(session, task, d["decision"] == "approve", d.get("comment"),
                   UUID(d["moderator_id"]) if d.get("moderator_id") else None)


async def on_video_event(envelope: Envelope, session: AsyncSession) -> None:
    """Сервер видеосвязи: ученик начал или прекратил показывать экран в тесте с прокторингом.
    Без показа ответы не принимаются (api/assignments.py, _screen_ok)."""
    if envelope.type != "video.proctor.screen":
        return
    d = envelope.data
    at = datetime.fromisoformat(d["at"])
    attempt = await session.scalar(
        select(Attempt).where(Attempt.assignment_id == UUID(d["assignment_id"]), Attempt.student_id == UUID(d["student_id"]),
                              Attempt.status == IN_PROGRESS).with_for_update()
    )
    if attempt is None or (attempt.screen_changed_at and attempt.screen_changed_at > at):
        return  # попытка уже сдана или событие запоздало
    changed = attempt.screen_sharing != bool(d["sharing"])
    attempt.screen_sharing, attempt.screen_changed_at = bool(d["sharing"]), at
    if changed:
        a = await session.get(Assignment, attempt.assignment_id)
        # Уже записано — страница ученика (шторка) и наблюдение педагога обновятся сразу (chat → WebSocket).
        await outbox.event(session, "assessment.attempt.screen", {
            "attempt_id": str(attempt.id), "assignment_id": str(attempt.assignment_id), "student_id": str(attempt.student_id),
            "teacher_id": str(a.teacher_id), "sharing": attempt.screen_sharing, "watcher_ids": await class_access.watchers(a),
        })
