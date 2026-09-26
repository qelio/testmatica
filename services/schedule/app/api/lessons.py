from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import logic
from ..config import settings
from ..deps import auth, classroom, db
from ..models import (
    KIND_GROUP,
    KIND_INDIVIDUAL,
    REQUEST_PENDING,
    STATUS_SCHEDULED,
    Lesson,
    LessonParticipant,
    LessonSeries,
    RescheduleRequest,
)
from ..recurrence import expand, zone
from ..schemas import CancelRequest, CreatedLessons, LessonCreate, LessonOut, LessonUpdate, RescheduleCreate

router = APIRouter(prefix="/lessons", tags=["lessons"])
teacher = auth.require(ROLE_TEACHER)

MAX_RANGE = timedelta(days=62)


@router.get("", response_model=list[LessonOut])
async def calendar(
    start: datetime = Query(alias="from"),
    end: datetime = Query(alias="to"),
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> list[LessonOut]:
    """Календарь: для педагога — все его занятия (оба режима), для ученика — занятия, где он участник."""
    if end <= start or end - start > MAX_RANGE:
        raise ApiError(422, "invalid_range", "Период — не больше 62 дней")
    query = select(Lesson).where(Lesson.starts_at < end, Lesson.ends_at > start)
    if principal.has_any(ROLE_TEACHER):
        query = query.where(Lesson.teacher_id == principal.user_id)
    else:
        query = query.join(LessonParticipant, LessonParticipant.lesson_id == Lesson.id).where(
            LessonParticipant.student_id == principal.user_id
        )
    lessons = (await session.execute(query.order_by(Lesson.starts_at))).scalars().all()
    return await logic.serialize(session, lessons, principal)


@router.post("", response_model=CreatedLessons, status_code=201)
async def create_lessons(
    body: LessonCreate, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> CreatedLessons:
    group_title = None
    subject = body.subject
    if body.kind == KIND_GROUP:
        group = await classroom.get(f"/internal/groups/{body.group_id}", params={"teacher_id": str(principal.user_id)})
        if group["archived"]:
            raise ApiError(409, "group_archived", "Группа в архиве")
        paid, group_title, student_ids = group["paid"], group["title"], [UUID(s) for s in group["member_ids"]]
        subject = subject or group["subject"]
    else:
        link = await classroom.get(
            "/internal/links", params={"teacher_id": str(principal.user_id), "student_id": str(body.student_id)}
        )
        if not link["active"]:
            raise ApiError(404, "student_not_found", "Ученик не привязан к вам")
        paid, student_ids = link.get("paid", False), [body.student_id]
    if body.paid is not None:
        paid = body.paid  # педагог поменял для этих занятий (например, пробное — бесплатно)

    zone(body.timezone)
    duration = timedelta(minutes=body.duration_min)
    series = None
    if body.repeat:
        starts = expand(
            body.starts_at,
            body.timezone,
            body.repeat.weekdays,
            body.repeat.interval_weeks,
            body.repeat.until,
            body.repeat.count,
            settings.series_max_lessons,
            settings.series_max_days,
        )
        series = LessonSeries(
            teacher_id=principal.user_id, rule=body.repeat.model_dump(mode="json"), timezone=body.timezone
        )
        session.add(series)
        await session.flush()
    else:
        starts = [body.starts_at]

    await logic.check_conflicts(session, principal.user_id, [(s, s + duration) for s in starts])
    lessons = [
        Lesson(
            series_id=series.id if series else None,
            teacher_id=principal.user_id,
            paid=paid,
            kind=body.kind,
            group_id=body.group_id if body.kind == KIND_GROUP else None,
            group_title=group_title,
            student_id=body.student_id if body.kind == KIND_INDIVIDUAL else None,
            subject=subject,
            topic=body.topic,
            exam_item_ids=list(dict.fromkeys(body.exam_item_ids or [])),
            starts_at=s,
            ends_at=s + duration,
            video_url=body.video_url,
            status=STATUS_SCHEDULED,
        )
        for s in starts
    ]
    session.add_all(lessons)
    await logic.flush_or_conflict(session)
    session.add_all(LessonParticipant(lesson_id=lesson.id, student_id=sid) for lesson in lessons for sid in student_ids)
    logic.plan_reminders(session, lessons)
    await session.flush()
    await logic.publish(session, "schedule.lesson.created", lessons, principal.user_id)
    await session.commit()
    return CreatedLessons(count=len(lessons), lessons=await logic.serialize(session, lessons[:1], principal))


@router.get("/{lesson_id}", response_model=LessonOut)
async def get_lesson(
    lesson_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> LessonOut:
    lesson = await logic.visible_lesson(session, lesson_id, principal)
    return (await logic.serialize(session, [lesson], principal))[0]


async def _following(session: AsyncSession, lesson: Lesson) -> list[Lesson]:
    """Это занятие и все следующие в серии (отменённые не трогаем)."""
    if lesson.series_id is None:
        return [lesson]
    rows = await session.execute(
        select(Lesson)
        .where(
            Lesson.series_id == lesson.series_id,
            Lesson.starts_at >= lesson.starts_at,
            Lesson.status == STATUS_SCHEDULED,
        )
        .order_by(Lesson.starts_at)
        .with_for_update()
    )
    return list(rows.scalars())


@router.patch("/{lesson_id}", response_model=LessonOut)
async def update_lesson(
    lesson_id: UUID,
    body: LessonUpdate,
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> LessonOut:
    lesson = await logic.visible_lesson(session, lesson_id, principal, lock=True)
    logic.require_owner(lesson, principal)
    if lesson.status != STATUS_SCHEDULED:
        raise ApiError(409, "lesson_cancelled", "Занятие отменено")
    data = body.model_dump(exclude_unset=True, exclude={"scope"})
    new_start = data.pop("starts_at", None)
    targets = await _following(session, lesson) if body.scope == "following" else [lesson]

    # Длительность и время меняются вместе — сначала посчитаем новые интервалы и проверим пересечения.
    delta = (new_start - lesson.starts_at) if new_start and body.scope == "following" else timedelta(0)
    duration = timedelta(minutes=data.pop("duration_min")) if "duration_min" in data else None
    if delta or duration:
        intervals = []
        for t in targets:
            start = t.starts_at + delta
            intervals.append((start, start + (duration or (t.ends_at - t.starts_at))))
        await logic.check_conflicts(session, lesson.teacher_id, intervals, exclude=[t.id for t in targets])
        for t, (start, end) in zip(targets, intervals, strict=True):
            t.starts_at, t.ends_at = start, end
        await logic.flush_or_conflict(session)
        logic.plan_reminders(session, targets)

    if data.get("paid") is None:
        data.pop("paid", None)
    if "exam_item_ids" in data:
        data["exam_item_ids"] = list(dict.fromkeys(data["exam_item_ids"] or []))
    for t in targets:
        for field, value in data.items():
            setattr(t, field, value)

    if delta or duration or data:
        await logic.publish(session, "schedule.lesson.updated", targets, principal.user_id, {"scope": body.scope})

    # Перенос одного занятия — отдельная логика: у индивидуального нужно согласие ученика.
    if new_start and body.scope == "this" and new_start != lesson.starts_at:
        await _reschedule(session, lesson, new_start, principal, comment=None)

    await session.commit()
    return (await logic.serialize(session, [lesson], principal))[0]


@router.post("/{lesson_id}/cancel", response_model=LessonOut)
async def cancel_lesson(
    lesson_id: UUID,
    body: CancelRequest,
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> LessonOut:
    """Педагог может отменить занятие в любой момент (ТЗ, раздел 6)."""
    lesson = await logic.visible_lesson(session, lesson_id, principal, lock=True)
    logic.require_owner(lesson, principal)
    if lesson.status != STATUS_SCHEDULED:
        raise ApiError(409, "lesson_cancelled", "Занятие уже отменено")
    targets = await _following(session, lesson) if body.scope == "following" else [lesson]
    await logic.cancel(session, targets, principal.user_id, body.reason)
    await session.commit()
    return (await logic.serialize(session, [lesson], principal))[0]


@router.post("/{lesson_id}/reschedule", response_model=LessonOut)
async def reschedule(
    lesson_id: UUID,
    body: RescheduleCreate,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> LessonOut:
    """Перенос одного занятия. Педагог переносит групповое занятие сразу; индивидуальное —
    после подтверждения ученика. Ученик может только предложить перенос индивидуального занятия."""
    lesson = await logic.visible_lesson(session, lesson_id, principal, lock=True)
    await _reschedule(session, lesson, body.starts_at, principal, body.comment)
    await session.commit()
    return (await logic.serialize(session, [lesson], principal))[0]


async def _reschedule(
    session: AsyncSession, lesson: Lesson, new_start: datetime, principal: Principal, comment: str | None
) -> None:
    if lesson.status != STATUS_SCHEDULED:
        raise ApiError(409, "lesson_cancelled", "Занятие отменено")
    if new_start.tzinfo is None:
        raise ApiError(422, "invalid_time", "Время нужно передавать с часовым поясом")
    is_teacher = lesson.teacher_id == principal.user_id
    if lesson.kind == KIND_GROUP:
        if not is_teacher:
            raise ApiError(403, "forbidden", "Групповое занятие переносит педагог")
        await logic.move(session, lesson, new_start, principal.user_id)
        return

    new_end = new_start + (lesson.ends_at - lesson.starts_at)
    # Время педагога должно быть свободно уже на этапе предложения.
    await logic.check_conflicts(session, lesson.teacher_id, [(new_start, new_end)], exclude=[lesson.id])
    await logic.cancel_pending_requests(session, [lesson.id])
    req = RescheduleRequest(
        lesson_id=lesson.id,
        requested_by=principal.user_id,
        new_starts_at=new_start,
        new_ends_at=new_end,
        comment=comment,
        status=REQUEST_PENDING,
    )
    session.add(req)
    await session.flush()
    await logic.publish(
        session,
        "schedule.reschedule.requested",
        [lesson],
        principal.user_id,
        {"request_id": str(req.id), "new_starts_at": new_start.isoformat(), "by_teacher": is_teacher},
    )
