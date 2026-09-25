from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_MODERATOR, Principal
from testmatica_common.errors import ApiError

from .deps import auth, db, outbox
from .models import APPROVED, KIND_LABELS, PENDING, REJECTED, Person, QueueItem

router = APIRouter(prefix="/queue", tags=["queue"])
moderator = auth.require(ROLE_MODERATOR)


class ItemOut(BaseModel):
    id: UUID
    kind: str
    kind_label: str
    ref_id: UUID
    title: str
    author_id: UUID
    author_name: str
    details: dict[str, Any]
    status: str
    comment: str | None
    decided_at: datetime | None
    created_at: datetime


class Decision(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _reason_for_reject(self) -> "Decision":
        self.comment = (self.comment or "").strip() or None
        if self.decision == "reject" and not self.comment:
            raise ValueError("Напишите, что нужно исправить")
        return self


async def _out(session: AsyncSession, items: list[QueueItem]) -> list[ItemOut]:
    ids = {i.author_id for i in items}
    names = dict((await session.execute(select(Person.user_id, Person.full_name).where(Person.user_id.in_(ids)))).all()) if ids else {}
    return [
        ItemOut(
            id=i.id, kind=i.kind, kind_label=KIND_LABELS.get(i.kind, i.kind), ref_id=i.ref_id, title=i.title,
            author_id=i.author_id, author_name=names.get(i.author_id, "Автор"), details=i.details, status=i.status,
            comment=i.comment, decided_at=i.decided_at, created_at=i.created_at,
        )
        for i in items
    ]


@router.get("", response_model=list[ItemOut])
async def queue(
    status: str = Query(PENDING),
    kind: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    _: Principal = Depends(moderator),
    session: AsyncSession = Depends(db.session),
) -> list[ItemOut]:
    query = select(QueueItem).where(QueueItem.status == status)
    if kind:
        query = query.where(QueueItem.kind == kind)
    if status == PENDING:
        query = query.order_by(QueueItem.priority.desc(), QueueItem.created_at)  # FIFO
    else:
        query = query.order_by(QueueItem.decided_at.desc().nulls_last())
    return await _out(session, list((await session.execute(query.limit(limit))).scalars()))


@router.get("/stats", response_model=dict[str, int])
async def stats(_: Principal = Depends(moderator), session: AsyncSession = Depends(db.session)) -> dict[str, int]:
    rows = await session.execute(
        select(QueueItem.kind, func.count()).where(QueueItem.status == PENDING).group_by(QueueItem.kind)
    )
    return dict(rows.all())


@router.post("/{item_id}/decide", response_model=ItemOut)
async def decide(
    item_id: UUID,
    body: Decision,
    principal: Principal = Depends(moderator),
    session: AsyncSession = Depends(db.session),
) -> ItemOut:
    item = await session.get(QueueItem, item_id, with_for_update=True)
    if item is None:
        raise ApiError(404, "not_found", "Заявка не найдена")
    if item.status != PENDING:
        raise ApiError(409, "already_decided", "По заявке уже принято решение или автор её отозвал")
    item.status = APPROVED if body.decision == "approve" else REJECTED
    item.comment = body.comment
    item.decided_by = principal.user_id
    item.decided_at = datetime.now(UTC)
    await outbox.event(
        session,
        "moderation.decision.made",
        {
            "item_id": str(item.id),
            "kind": item.kind,
            "ref_id": str(item.ref_id),
            "decision": body.decision,
            "comment": body.comment,
            "author_id": str(item.author_id),
            "moderator_id": str(principal.user_id),
            "title": item.title,
        },
        actor_id=principal.user_id,
    )
    await session.commit()
    return (await _out(session, [item]))[0]
