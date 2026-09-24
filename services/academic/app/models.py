from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from testmatica_common.ids import uuid7
from testmatica_common.messaging import messaging_tables

ATTENDANCE = ("present", "absent", "late", "sick")

# Типы оценок по умолчанию; дальше справочник ведёт модератор.
DEFAULT_GRADE_TYPES = (
    "Работа на уроке",
    "Домашняя работа",
    "Устный ответ",
    "Самостоятельная работа",
    "Контрольная работа",
)


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


class GradeType(Base):
    """Справочник типов оценок (задаёт модератор, без весов — ТЗ, раздел 8)."""

    __tablename__ = "grade_types"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Grade(Base):
    """Оценка ученику за занятие. За одно занятие может быть несколько оценок."""

    __tablename__ = "grades"
    __table_args__ = (
        CheckConstraint("value BETWEEN 1 AND 5", name="value_range"),
        CheckConstraint("length(trim(comment)) > 0", name="comment_required"),
        CheckConstraint("source IN ('manual', 'test')", name="source_valid"),
        Index("ix_grades_lesson", "lesson_id"),
        Index("ix_grades_student_time", "student_id", "lesson_starts_at"),
        Index("ix_grades_group_time", "group_id", "lesson_starts_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    teacher_id: Mapped[UUID]
    student_id: Mapped[UUID]
    lesson_id: Mapped[UUID]
    # Копия данных занятия на момент оценки — для журнала и аналитики без запросов в schedule.
    lesson_starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    group_id: Mapped[UUID | None]
    subject: Mapped[str | None] = mapped_column(String(80))
    value: Mapped[int] = mapped_column(SmallInteger)
    grade_type_id: Mapped[UUID] = mapped_column(ForeignKey("grade_types.id"))
    comment: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        CheckConstraint("status IN ('present', 'absent', 'late', 'sick')", name="status_valid"),
        Index("ix_attendance_student_time", "student_id", "lesson_starts_at"),
        Index("ix_attendance_group_time", "group_id", "lesson_starts_at"),
    )

    lesson_id: Mapped[UUID] = mapped_column(primary_key=True)
    student_id: Mapped[UUID] = mapped_column(primary_key=True)
    teacher_id: Mapped[UUID]
    lesson_starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    group_id: Mapped[UUID | None]
    subject: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(10))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
