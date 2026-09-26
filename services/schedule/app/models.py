from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Computed, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, false, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSTZRANGE, ExcludeConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from testmatica_common.ids import uuid7
from testmatica_common.messaging import messaging_tables

STATUS_SCHEDULED = "scheduled"
STATUS_CANCELLED = "cancelled"

KIND_INDIVIDUAL = "individual"
KIND_GROUP = "group"

REQUEST_PENDING = "pending"
REQUEST_ACCEPTED = "accepted"
REQUEST_DECLINED = "declined"
REQUEST_CANCELLED = "cancelled"


class Base(DeclarativeBase):
    pass


outbox, inbox = messaging_tables(Base.metadata)


class Person(Base):
    """Реплика имён пользователей из identity."""

    __tablename__ = "people"

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    login: Mapped[str | None] = mapped_column(String(64))
    roles: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LessonSeries(Base):
    """Правило повторения. Сами занятия серии создаются сразу и хранятся в lessons."""

    __tablename__ = "lesson_series"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    teacher_id: Mapped[UUID]
    # {"weekdays": [0, 2], "interval_weeks": 1, "until": "2026-12-31" | null, "count": 30 | null}
    rule: Mapped[dict[str, Any]] = mapped_column(JSONB)
    timezone: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (
        CheckConstraint("kind IN ('individual', 'group')", name="kind_valid"),
        CheckConstraint("status IN ('scheduled', 'cancelled')", name="status_valid"),
        CheckConstraint("ends_at > starts_at", name="ends_after_start"),
        CheckConstraint(
            "(kind = 'group' AND group_id IS NOT NULL) OR (kind = 'individual' AND student_id IS NOT NULL)",
            name="target_valid",
        ),
        # Главная защита от пересечений: у одного педагога не может быть двух
        # запланированных занятий, пересекающихся по времени (btree_gist).
        ExcludeConstraint(
            ("teacher_id", "="),
            ("period", "&&"),
            where=text("status = 'scheduled'"),
            using="gist",
            name="no_teacher_overlap",
        ),
        Index("ix_lessons_teacher_starts", "teacher_id", "starts_at"),
        Index("ix_lessons_group_starts", "group_id", "starts_at"),
        Index("ix_lessons_series", "series_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    series_id: Mapped[UUID | None] = mapped_column(ForeignKey("lesson_series.id", ondelete="SET NULL"))
    teacher_id: Mapped[UUID]
    # Платное занятие (оплата — этап 4) или бесплатное. Берётся от группы или ученика при создании,
    # у отдельного занятия можно поменять (например, пробное — бесплатно).
    paid: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Пробное занятие: после него ученику предлагается оставить отзыв и подтвердить продолжение (ТЗ, раздел 4).
    trial: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    kind: Mapped[str] = mapped_column(String(12))
    group_id: Mapped[UUID | None]
    group_title: Mapped[str | None] = mapped_column(String(120))
    student_id: Mapped[UUID | None]
    subject: Mapped[str | None] = mapped_column(String(80))
    topic: Mapped[str | None] = mapped_column(String(300))
    # Задания ЕГЭ/ОГЭ, которые разбираются на занятии (каталог — в assessment, здесь только id).
    exam_item_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid), default=list, server_default="{}")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Интервал занятия для ограничения no_teacher_overlap; считается базой.
    period = mapped_column(TSTZRANGE, Computed("tstzrange(starts_at, ends_at)", persisted=True))
    status: Mapped[str] = mapped_column(String(10), default=STATUS_SCHEDULED)
    video_url: Mapped[str | None] = mapped_column(String(500))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[UUID | None]
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @property
    def duration_min(self) -> int:
        return int((self.ends_at - self.starts_at).total_seconds() // 60)


class LessonParticipant(Base):
    """Ученики занятия. Для группового — состав группы на момент занятия
    (будущие занятия обновляются по событиям classroom)."""

    __tablename__ = "lesson_participants"
    __table_args__ = (Index("ix_participants_student", "student_id"),)

    lesson_id: Mapped[UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), primary_key=True)
    student_id: Mapped[UUID] = mapped_column(primary_key=True)


class RescheduleRequest(Base):
    """Перенос индивидуального занятия, ожидающий подтверждения второй стороны."""

    __tablename__ = "reschedule_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'accepted', 'declined', 'cancelled')", name="status_valid"),
        Index("ix_reschedule_lesson", "lesson_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    lesson_id: Mapped[UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"))
    requested_by: Mapped[UUID]
    new_starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    new_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(10), default=REQUEST_PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScheduledJob(Base):
    """Отложенные действия (напоминания). Хранятся в БД — переживают перезапуски."""

    __tablename__ = "scheduled_jobs"
    __table_args__ = (Index("ix_jobs_due", "run_at", postgresql_where=text("done_at IS NULL")),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    kind: Mapped[str] = mapped_column(String(32))
    lesson_id: Mapped[UUID] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"))
    # Время начала занятия, для которого создано напоминание: если занятие перенесли — задача устарела.
    lesson_starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
