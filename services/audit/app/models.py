from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from testmatica_common.messaging import messaging_tables


class Base(DeclarativeBase):
    pass


outbox, inbox = messaging_tables(Base.metadata)


class AuditRecord(Base):
    """Неизменяемый журнал всех событий платформы.
    UPDATE и DELETE запрещены триггером (см. миграцию)."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_occurred", "occurred_at"),
        Index("ix_audit_actor_occurred", "actor_id", "occurred_at"),
        Index("ix_audit_type_occurred", "type", "occurred_at"),
    )

    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(200))
    version: Mapped[int]
    producer: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[UUID | None]
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
