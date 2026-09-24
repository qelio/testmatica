from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
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
    before: datetime | None = None,
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(db.session),
) -> list[AuditRecordOut]:
    query = select(AuditRecord)
    if type_prefix:
        query = query.where(AuditRecord.type.startswith(type_prefix, autoescape=True))
    if actor_id:
        query = query.where(AuditRecord.actor_id == actor_id)
    if before:
        query = query.where(AuditRecord.occurred_at < before)
    rows = (await session.execute(query.order_by(AuditRecord.occurred_at.desc()).limit(limit))).scalars()
    return [AuditRecordOut.model_validate(r, from_attributes=True) for r in rows]
