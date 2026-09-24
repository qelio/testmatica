"""Запросы на перенос индивидуальных занятий: подтверждение второй стороной."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal
from testmatica_common.errors import ApiError

from .. import logic
from ..deps import auth, db
from ..models import (
    REQUEST_ACCEPTED,
    REQUEST_CANCELLED,
    REQUEST_DECLINED,
    REQUEST_PENDING,
    Lesson,
    RescheduleRequest,
)
from ..schemas import RescheduleWithLesson

router = APIRouter(prefix="/reschedule-requests", tags=["reschedule"])


async def _load(session: AsyncSession, request_id: UUID, principal: Principal) -> tuple[RescheduleRequest, Lesson]:
    req = await session.get(RescheduleRequest, request_id, with_for_update=True)
    if req is None or req.status != REQUEST_PENDING:
        raise ApiError(404, "request_not_found", "Запрос не найден или уже обработан")
    lesson = await logic.visible_lesson(session, req.lesson_id, principal, lock=True)
    return req, lesson


@router.get("", response_model=list[RescheduleWithLesson])
async def pending_requests(
    principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> list[RescheduleWithLesson]:
    """Ожидающие запросы по моим занятиям — и входящие, и отправленные мной."""
    rows = await session.execute(
        select(RescheduleRequest, Lesson)
        .join(Lesson, Lesson.id == RescheduleRequest.lesson_id)
        .where(
            RescheduleRequest.status == REQUEST_PENDING,
            or_(Lesson.teacher_id == principal.user_id, Lesson.student_id == principal.user_id),
        )
        .order_by(RescheduleRequest.created_at)
    )
    pairs = rows.all()
    serialized = await logic.serialize(session, [lesson for _, lesson in pairs], principal)
    lessons = {out.id: out for out in serialized}
    return [
        RescheduleWithLesson(**logic.reschedule_out(req, principal).model_dump(), lesson=lessons[lesson.id])
        for req, lesson in pairs
    ]


@router.post("/{request_id}/accept", status_code=204)
async def accept(
    request_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> None:
    req, lesson = await _load(session, request_id, principal)
    if req.requested_by == principal.user_id:
        raise ApiError(403, "forbidden", "Подтвердить перенос должна другая сторона")
    await logic.move(session, lesson, req.new_starts_at, principal.user_id)
    req.status = REQUEST_ACCEPTED
    req.responded_at = logic.now()
    await session.commit()


@router.post("/{request_id}/decline", status_code=204)
async def decline(
    request_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> None:
    req, lesson = await _load(session, request_id, principal)
    if req.requested_by == principal.user_id:
        raise ApiError(403, "forbidden", "Свой запрос можно только отозвать")
    req.status = REQUEST_DECLINED
    req.responded_at = logic.now()
    by_teacher = req.requested_by == lesson.teacher_id
    await logic.publish(
        session,
        "schedule.reschedule.declined",
        [lesson],
        principal.user_id,
        {"request_id": str(req.id), "requested_by": str(req.requested_by)},
    )
    if by_teacher:
        # decisions.md, п. 13: ученик не согласился с переносом — это отмена занятия педагогом.
        await logic.cancel(session, [lesson], lesson.teacher_id, "Ученик не согласился с переносом")
    await session.commit()


@router.delete("/{request_id}", status_code=204)
async def withdraw(
    request_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> None:
    req, _ = await _load(session, request_id, principal)
    if req.requested_by != principal.user_id:
        raise ApiError(403, "forbidden", "Отозвать можно только свой запрос")
    req.status = REQUEST_CANCELLED
    req.responded_at = logic.now()
    await session.commit()
