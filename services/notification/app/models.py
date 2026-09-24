from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from testmatica_common.ids import uuid7
from testmatica_common.messaging import messaging_tables


class Base(DeclarativeBase):
    pass


outbox, inbox = messaging_tables(Base.metadata)


class Notification(Base):
    """Уведомление в интерфейсе (колокольчик)."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_created", "user_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailDelivery(Base):
    """Журнал отправленных писем. Адрес хранится, содержимое письма (коды) — нет."""

    __tablename__ = "email_deliveries"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    command_id: Mapped[UUID] = mapped_column(unique=True)
    to: Mapped[str] = mapped_column(String(254))
    template: Mapped[str] = mapped_column(String(64))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
