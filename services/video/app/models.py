from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid, false, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from testmatica_common.ids import uuid7
from testmatica_common.messaging import messaging_tables

RECORDING, READY, FAILED, EXPIRED = "recording", "ready", "failed", "expired"


class Base(DeclarativeBase):
    pass


outbox, inbox = messaging_tables(Base.metadata)


class Person(Base):
    """Реплика имён из identity — подписи участников в комнате."""

    __tablename__ = "people"

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))


class Room(Base):
    """Видеокомната занятия. Одна на занятие; в LiveKit называется lesson-<id>."""

    __tablename__ = "rooms"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    lesson_id: Mapped[UUID] = mapped_column(unique=True)
    teacher_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(12))
    group_id: Mapped[UUID | None]
    title: Mapped[str] = mapped_column(String(200))
    max_participants: Mapped[int] = mapped_column(Integer)
    time_limit_min: Mapped[int | None] = mapped_column(Integer)  # None — без ограничения (платные занятия, подписка)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # первый вход
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(String(20))  # teacher / time_limit / empty
    # Ученики, которым педагог разрешил показывать экран.
    screen_share: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid), default=list, server_default="{}")
    # Запись включается сама, когда в комнату входит участник (решение №40); педагог остановил вручную — больше не включается.
    auto_record_off: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def livekit_name(self) -> str:
        return f"lesson-{self.lesson_id}"


class Connection(Base):
    """Лог подключений (ТЗ: для споров об оплате — кто, когда и сколько был на занятии)."""

    __tablename__ = "connections"
    __table_args__ = (Index("ix_connections_room_user", "room_id", "user_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    room_id: Mapped[UUID] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    user_id: Mapped[UUID]
    livekit_sid: Mapped[str] = mapped_column(String(64), unique=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Recording(Base):
    """Запись занятия (MP4 в S3). Доступ — педагогу и ученикам занятия (ТЗ, раздел 7)."""

    __tablename__ = "recordings"
    __table_args__ = (
        CheckConstraint("status IN ('recording', 'ready', 'failed', 'expired')", name="status_valid"),
        Index("ix_recordings_teacher", "teacher_id", "status", "started_at"),
        Index("ix_recordings_viewers", "viewer_ids", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    room_id: Mapped[UUID] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    lesson_id: Mapped[UUID]
    teacher_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String(200))
    viewer_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid), default=list)  # ученики занятия на момент записи
    egress_id: Mapped[str] = mapped_column(String(64), unique=True)
    key: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(10), default=RECORDING)
    size: Mapped[int | None] = mapped_column(BigInteger)
    duration_s: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Egress запускает Chrome несколько секунд: до active_at запись ещё не пишется, остановить её нельзя.
    active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stop_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(300))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class ProctorRecording(Base):
    """Запись экрана ученика в тесте с прокторингом (WebM в S3, по дорожке). Хранится 14 дней, видит педагог (ТЗ, раздел 7).
    Если ученик перезапускал показ экрана — у попытки несколько файлов."""

    __tablename__ = "proctor_recordings"
    __table_args__ = (
        CheckConstraint("status IN ('recording', 'ready', 'failed', 'expired')", name="status_valid"),
        Index("ix_proctor_recordings_assignment", "assignment_id", "student_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    assignment_id: Mapped[UUID]
    teacher_id: Mapped[UUID]
    student_id: Mapped[UUID]
    attempt_id: Mapped[UUID | None]
    title: Mapped[str] = mapped_column(String(200))
    track_sid: Mapped[str] = mapped_column(String(64))
    egress_id: Mapped[str] = mapped_column(String(64), unique=True)
    key: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(10), default=RECORDING)
    size: Mapped[int | None] = mapped_column(BigInteger)
    duration_s: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(300))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
