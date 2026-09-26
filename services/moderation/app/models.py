from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from testmatica_common.ids import uuid7
from testmatica_common.messaging import messaging_tables

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
WITHDRAWN = "withdrawn"

# Что проверяют модераторы. Новые виды (задачи, отзывы, документы педагогов) добавляются сюда.
KIND_LABELS = {
    "course": "Курс в публичную библиотеку",
    "task": "Задача в публичный банк",
    "plan_template": "КТП в публичную библиотеку",
    "education_doc": "Документ об образовании",
}


class Base(DeclarativeBase):
    pass


outbox, inbox = messaging_tables(Base.metadata)


class Person(Base):
    __tablename__ = "people"

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))


class QueueItem(Base):
    """Заявка на проверку. Очередь — FIFO (ТЗ): сначала приоритет (подписка), затем время поступления."""

    __tablename__ = "queue_items"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'withdrawn')", name="status_valid"),
        # По одному объекту — не больше одной открытой заявки.
        Index("uq_queue_open", "kind", "ref_id", unique=True, postgresql_where=text("status = 'pending'")),
        Index("ix_queue_pending", "status", "priority", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    kind: Mapped[str] = mapped_column(String(32))
    ref_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String(300))
    author_id: Mapped[UUID]
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10), default=PENDING)
    comment: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[UUID | None]
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
