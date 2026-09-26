from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Date, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_ADMIN

from ..deps import auth, db
from ..models import AuditRecord

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(auth.require(ROLE_ADMIN))])


class AuditRecordOut(BaseModel):
    event_id: UUID
    type: str
    producer: str
    actor_id: UUID | None
    occurred_at: datetime
    data: dict[str, Any]


@router.get("", response_model=list[AuditRecordOut])
async def list_records(
    type_prefix: str | None = Query(None, description="Например, identity.user"),
    actor_id: UUID | None = None,
    user_id: UUID | None = Query(None, description="История пользователя: он действовал или действие касалось его"),
    before: datetime | None = None,
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(db.session),
) -> list[AuditRecordOut]:
    query = select(AuditRecord)
    if type_prefix:
        query = query.where(AuditRecord.type.startswith(type_prefix, autoescape=True))
    if actor_id:
        query = query.where(AuditRecord.actor_id == actor_id)
    if user_id:
        query = query.where(or_(AuditRecord.actor_id == user_id, AuditRecord.data.contains({"user_id": str(user_id)})))
    if before:
        query = query.where(AuditRecord.occurred_at < before)
    rows = (await session.execute(query.order_by(AuditRecord.occurred_at.desc()).limit(limit))).scalars()
    return [AuditRecordOut.model_validate(r, from_attributes=True) for r in rows]


# Что считаем активностью контента и учёбы: событие → подпись. У серии занятий в событии есть count.
ACTIVITY = {
    "schedule.lesson.created": "Занятий запланировано",
    "video.room.started": "Видеозанятий проведено",
    "assessment.assignment.created": "Тестов назначено",
    "assessment.attempt.submitted": "Работ сдано",
    "academic.grade.created": "Оценок поставлено",
    "chat.message.created": "Сообщений в чатах",
    "content.course.published": "Курсов опубликовано",
    "assessment.task.published": "Задач опубликовано",
    "marketplace.deal.agreed": "Договорились с репетитором",
}
# Действия педагога — для «топа педагогов».
TEACHER_ACTIONS = ("schedule.lesson.created", "assessment.assignment.created", "academic.grade.created", "video.room.started")


class ActivityLine(BaseModel):
    type: str
    title: str
    total: int
    by_day: dict[date, int]


class TopActor(BaseModel):
    actor_id: UUID
    actions: int


class AuditStats(BaseModel):
    activity: list[ActivityLine]
    top_teachers: list[TopActor]


@router.get("/stats", response_model=AuditStats)
async def stats(days: int = Query(30, ge=1, le=365), session: AsyncSession = Depends(db.session)) -> AuditStats:
    """Активность платформы по событиям за период и самые активные педагоги (по действиям в учёбе)."""
    since = datetime.now(UTC) - timedelta(days=days)
    day = cast(func.timezone("UTC", AuditRecord.occurred_at), Date)
    # Серия занятий — одно событие с count: считаем занятия, а не события.
    amount = func.coalesce(AuditRecord.data["count"].as_integer(), 1)
    rows = (await session.execute(
        select(AuditRecord.type, day, func.sum(amount))
        .where(AuditRecord.occurred_at >= since, AuditRecord.type.in_(list(ACTIVITY)))
        .group_by(AuditRecord.type, day)
    )).all()
    by_type: dict[str, dict[date, int]] = {t: {} for t in ACTIVITY}
    for t, d, n in rows:
        by_type[t][d] = int(n)
    top = (await session.execute(
        select(AuditRecord.actor_id, func.count())
        .where(AuditRecord.occurred_at >= since, AuditRecord.type.in_(TEACHER_ACTIONS), AuditRecord.actor_id.is_not(None))
        .group_by(AuditRecord.actor_id).order_by(func.count().desc()).limit(10)
    )).all()
    return AuditStats(
        activity=[ActivityLine(type=t, title=ACTIVITY[t], total=sum(v.values()), by_day=v) for t, v in by_type.items()],
        top_teachers=[TopActor(actor_id=a, actions=n) for a, n in top],
    )
