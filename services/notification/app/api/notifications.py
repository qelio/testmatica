from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal
from testmatica_common.errors import ApiError

from ..deps import auth, db
from ..models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: UUID
    kind: str
    title: str
    body: str
    payload: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationOut]
    unread: int


@router.get("", response_model=NotificationList)
async def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    before: datetime | None = None,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> NotificationList:
    query = select(Notification).where(Notification.user_id == principal.user_id)
    if before is not None:
        query = query.where(Notification.created_at < before)
    rows = (await session.execute(query.order_by(Notification.created_at.desc()).limit(limit))).scalars()
    unread = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == principal.user_id, Notification.read_at.is_(None))
    )
    return NotificationList(
        items=[NotificationOut.model_validate(n, from_attributes=True) for n in rows], unread=unread or 0
    )


@router.post("/{notification_id}/read", status_code=204)
async def mark_read(
    notification_id: UUID,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> None:
    result = await session.execute(
        update(Notification)
        .where(Notification.id == notification_id, Notification.user_id == principal.user_id)
        .values(read_at=func.coalesce(Notification.read_at, datetime.now(UTC)))
    )
    if result.rowcount == 0:
        raise ApiError(404, "not_found", "Уведомление не найдено")
    await session.commit()


@router.post("/read-all", status_code=204)
async def mark_all_read(
    principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> None:
    await session.execute(
        update(Notification)
        .where(Notification.user_id == principal.user_id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await session.commit()
