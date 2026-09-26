"""Операции с занятиями. События публикуются здесь, в той же транзакции, что и изменения."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal
from testmatica_common.errors import ApiError

from . import people
from .config import settings
from .deps import outbox
from .models import (
    KIND_GROUP,
    REQUEST_CANCELLED,
    REQUEST_PENDING,
    STATUS_CANCELLED,
    STATUS_SCHEDULED,
    Lesson,
    LessonParticipant,
    RescheduleRequest,
    ScheduledJob,
)
from .schemas import LessonOut, Person, RescheduleOut

JOB_REMINDER = "reminder"


def now() -> datetime:
    return datetime.now(UTC)


# ---------- доступ ----------


async def participant_ids(session: AsyncSession, lesson_ids: Sequence[UUID]) -> dict[UUID, list[UUID]]:
    result: dict[UUID, list[UUID]] = defaultdict(list)
    if lesson_ids:
        rows = await session.execute(
            select(LessonParticipant.lesson_id, LessonParticipant.student_id).where(
                LessonParticipant.lesson_id.in_(lesson_ids)
            )
        )
        for lesson_id, student_id in rows.all():
            result[lesson_id].append(student_id)
    return result


async def visible_lesson(session: AsyncSession, lesson_id: UUID, principal: Principal, lock: bool = False) -> Lesson:
    """Занятие видно педагогу-владельцу и ученикам-участникам."""
    lesson = await session.get(Lesson, lesson_id, with_for_update=lock)
    if lesson is not None:
        if lesson.teacher_id == principal.user_id:
            return lesson
        member = await session.get(LessonParticipant, (lesson.id, principal.user_id))
        if member is not None:
            return lesson
    raise ApiError(404, "lesson_not_found", "Занятие не найдено")


def require_owner(lesson: Lesson, principal: Principal) -> None:
    if lesson.teacher_id != principal.user_id:
        raise ApiError(403, "forbidden", "Это может сделать только педагог")


# ---------- пересечения ----------


async def check_conflicts(
    session: AsyncSession,
    teacher_id: UUID,
    intervals: Sequence[tuple[datetime, datetime]],
    exclude: Sequence[UUID] = (),
) -> None:
    """Дружелюбная проверка до записи. Окончательную гарантию даёт ограничение в БД."""
    if not intervals:
        return
    query = select(Lesson).where(
        Lesson.teacher_id == teacher_id,
        Lesson.status == STATUS_SCHEDULED,
        or_(*(and_(Lesson.starts_at < end, Lesson.ends_at > start) for start, end in intervals)),
    )
    if exclude:
        query = query.where(Lesson.id.not_in(exclude))
    conflicts = (await session.execute(query.order_by(Lesson.starts_at).limit(5))).scalars().all()
    if conflicts:
        raise conflict_error(conflicts)


def conflict_error(conflicts: Sequence[Lesson] = ()) -> ApiError:
    return ApiError(
        409,
        "lesson_conflict",
        "В это время у вас уже есть занятие",
        {"conflicts": [{"lesson_id": str(c.id), "starts_at": c.starts_at.isoformat(), "ends_at": c.ends_at.isoformat()} for c in conflicts]},
    )


async def flush_or_conflict(session: AsyncSession) -> None:
    """Если параллельный запрос успел занять время — ограничение БД вернёт ошибку, отдаём 409."""
    try:
        await session.flush()
    except IntegrityError as e:
        if "no_teacher_overlap" in str(e.orig):
            raise conflict_error() from None
        raise


# ---------- напоминания ----------


def plan_reminders(session: AsyncSession, lessons: Sequence[Lesson]) -> None:
    moment = now()
    for lesson in lessons:
        for hours in settings.reminder_hours:
            run_at = lesson.starts_at - timedelta(hours=hours)
            if run_at > moment:
                session.add(
                    ScheduledJob(
                        kind=JOB_REMINDER,
                        lesson_id=lesson.id,
                        lesson_starts_at=lesson.starts_at,
                        payload={"hours": hours},
                        run_at=run_at,
                    )
                )


# ---------- события ----------


async def lesson_title(session: AsyncSession, lesson: Lesson) -> str:
    if lesson.kind == KIND_GROUP:
        return lesson.group_title or "Группа"
    return (await people.names(session, [lesson.student_id])).get(lesson.student_id, people.UNKNOWN_NAME)


async def publish(
    session: AsyncSession,
    type_: str,
    lessons: Sequence[Lesson],
    actor_id: UUID,
    extra: dict | None = None,
) -> None:
    """Одно событие на операцию (серия из 30 занятий — одно уведомление, а не 30)."""
    first = min(lessons, key=lambda lesson: lesson.starts_at)
    students = await participant_ids(session, [lesson.id for lesson in lessons])
    student_ids = sorted({str(s) for ids in students.values() for s in ids})
    teacher_name = (await people.names(session, [first.teacher_id])).get(first.teacher_id, people.UNKNOWN_NAME)
    await outbox.event(
        session,
        type_,
        {
            "lesson_ids": [str(lesson.id) for lesson in lessons],
            "count": len(lessons),
            "teacher_id": str(first.teacher_id),
            "teacher_name": teacher_name,
            "student_ids": student_ids,
            "title": await lesson_title(session, first),
            "subject": first.subject,
            "paid": first.paid,
            "kind": first.kind,
            "starts_at": first.starts_at.isoformat(),
            "ends_at": first.ends_at.isoformat(),
        }
        | (extra or {}),
        actor_id=actor_id,
    )


# ---------- изменения ----------


async def cancel_pending_requests(session: AsyncSession, lesson_ids: Sequence[UUID]) -> None:
    rows = await session.execute(
        select(RescheduleRequest).where(
            RescheduleRequest.lesson_id.in_(lesson_ids), RescheduleRequest.status == REQUEST_PENDING
        )
    )
    for req in rows.scalars():
        req.status = REQUEST_CANCELLED
        req.responded_at = now()


async def cancel(session: AsyncSession, lessons: Sequence[Lesson], actor_id: UUID, reason: str | None) -> None:
    active = [lesson for lesson in lessons if lesson.status == STATUS_SCHEDULED]
    if not active:
        return
    for lesson in active:
        lesson.status = STATUS_CANCELLED
        lesson.cancelled_at = now()
        lesson.cancelled_by = actor_id
        lesson.cancel_reason = reason
    await cancel_pending_requests(session, [lesson.id for lesson in active])
    await publish(session, "schedule.lesson.cancelled", active, actor_id, {"reason": reason})


async def move(session: AsyncSession, lesson: Lesson, new_start: datetime, actor_id: UUID) -> None:
    """Перенести занятие сейчас же (без подтверждения)."""
    if lesson.status != STATUS_SCHEDULED:
        raise ApiError(409, "lesson_cancelled", "Занятие отменено")
    duration = lesson.ends_at - lesson.starts_at
    new_end = new_start + duration
    await check_conflicts(session, lesson.teacher_id, [(new_start, new_end)], exclude=[lesson.id])
    old_start = lesson.starts_at
    lesson.starts_at, lesson.ends_at = new_start, new_end
    await flush_or_conflict(session)
    await cancel_pending_requests(session, [lesson.id])
    plan_reminders(session, [lesson])
    await publish(session, "schedule.lesson.rescheduled", [lesson], actor_id, {"old_starts_at": old_start.isoformat()})


# ---------- представление ----------


async def serialize(session: AsyncSession, lessons: Sequence[Lesson], principal: Principal) -> list[LessonOut]:
    ids = [lesson.id for lesson in lessons]
    students = await participant_ids(session, ids)
    names = await people.names(
        session,
        {lesson.teacher_id for lesson in lessons}
        | {lesson.student_id for lesson in lessons if lesson.student_id}
        | {s for ids_ in students.values() for s in ids_},
    )
    pending: dict[UUID, RescheduleRequest] = {}
    if ids:
        rows = await session.execute(
            select(RescheduleRequest).where(
                RescheduleRequest.lesson_id.in_(ids), RescheduleRequest.status == REQUEST_PENDING
            )
        )
        pending = {r.lesson_id: r for r in rows.scalars()}

    def name(uid: UUID) -> str:
        return names.get(uid, people.UNKNOWN_NAME)

    result = []
    for lesson in lessons:
        is_teacher = lesson.teacher_id == principal.user_id
        req = pending.get(lesson.id)
        result.append(
            LessonOut(
                id=lesson.id,
                series_id=lesson.series_id,
                teacher=Person(id=lesson.teacher_id, full_name=name(lesson.teacher_id)),
                paid=lesson.paid,
                kind=lesson.kind,
                group_id=lesson.group_id,
                # Педагогу индивидуальное занятие подписано именем ученика, ученику — именем педагога.
                title=(lesson.group_title or "Группа")
                if lesson.kind == KIND_GROUP
                else name(lesson.student_id if is_teacher else lesson.teacher_id),
                subject=lesson.subject,
                topic=lesson.topic,
                exam_item_ids=lesson.exam_item_ids or [],
                starts_at=lesson.starts_at,
                ends_at=lesson.ends_at,
                duration_min=lesson.duration_min,
                status=lesson.status,
                video_url=lesson.video_url,
                cancel_reason=lesson.cancel_reason,
                participants=sorted(
                    (Person(id=s, full_name=name(s)) for s in students[lesson.id]), key=lambda p: p.full_name
                )
                if is_teacher
                else None,
                pending_reschedule=reschedule_out(req, principal) if req else None,
            )
        )
    return result


def reschedule_out(req: RescheduleRequest, principal: Principal) -> RescheduleOut:
    return RescheduleOut(
        id=req.id,
        lesson_id=req.lesson_id,
        requested_by=req.requested_by,
        requested_by_me=req.requested_by == principal.user_id,
        new_starts_at=req.new_starts_at,
        new_ends_at=req.new_ends_at,
        comment=req.comment,
        status=req.status,
        created_at=req.created_at,
    )


async def remove_future_participation(session: AsyncSession, student_id: UUID, lesson_filter) -> None:
    future = select(Lesson.id).where(lesson_filter, Lesson.starts_at > now(), Lesson.status == STATUS_SCHEDULED)
    await session.execute(
        delete(LessonParticipant).where(
            LessonParticipant.student_id == student_id, LessonParticipant.lesson_id.in_(future)
        )
    )
