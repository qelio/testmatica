from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from testmatica_common.ids import uuid7
from testmatica_common.messaging import messaging_tables


class Base(DeclarativeBase):
    pass


outbox, inbox = messaging_tables(Base.metadata)


class StoredFile(Base):
    """Файл в S3. Доступ к скачиванию решает сервис, к сущности которого файл прикреплён
    (chat — участникам чата, assessment — ученику и педагогу и т. д.)."""

    __tablename__ = "files"
    __table_args__ = (
        CheckConstraint("status IN ('ready', 'deleted')", name="status_valid"),
        Index("ix_files_owner", "owner_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_id: Mapped[UUID]
    purpose: Mapped[str] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(200))
    mime: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(BigInteger)
    key: Mapped[str] = mapped_column(String(300), unique=True)
    status: Mapped[str] = mapped_column(String(10), default="ready")
    # Какой сервис «забрал» файл (прикрепил к сообщению, ответу…). Незабранные можно удалять.
    claimed_by: Mapped[str | None] = mapped_column(String(32))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
