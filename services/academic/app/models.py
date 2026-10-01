from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
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
    """Оценка ученику за занятие (за одно занятие — сколько угодно) или за работу из assessment —
    отдельной колонкой журнала без урока (lesson_id пуст, source_ref — id работы, title — её название)."""

    __tablename__ = "grades"
    __table_args__ = (
        CheckConstraint("value BETWEEN 1 AND 5", name="value_range"),
        CheckConstraint("length(trim(comment)) > 0", name="comment_required"),
        CheckConstraint("source IN ('manual', 'test')", name="source_valid"),
        Index("ix_grades_lesson", "lesson_id"),
        Index("ix_grades_student_time", "student_id", "lesson_starts_at"),
        Index("ix_grades_group_time", "group_id", "lesson_starts_at"),
        Index("ix_grades_teacher_works", "teacher_id", "lesson_starts_at", postgresql_where=text("lesson_id IS NULL")),
        Index("uq_grades_test_ref", "source_ref", "student_id", unique=True, postgresql_where=text("source = 'test'")),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    teacher_id: Mapped[UUID]
    student_id: Mapped[UUID]
    lesson_id: Mapped[UUID | None]
    # Копия данных занятия на момент оценки — для журнала и аналитики без запросов в schedule.
    # У оценки за работу без урока — когда работа назначена.
    lesson_starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    title: Mapped[str | None] = mapped_column(String(200))  # название работы — заголовок её колонки
    group_id: Mapped[UUID | None]
    subject: Mapped[str | None] = mapped_column(String(80))
    value: Mapped[int] = mapped_column(SmallInteger)
    grade_type_id: Mapped[UUID] = mapped_column(ForeignKey("grade_types.id"))
    comment: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), default="manual")
    # Для оценок из тестов — id выданной работы: переназначение обновляет оценку, а не дублирует.
    source_ref: Mapped[UUID | None]
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


# ---------- учебное планирование (КТП) ----------
# Материалы «к уроку» и «на дом» — список ссылок: [{"kind": "module" | "test" | "link" | "note", "ref_id", "title", "url"}].
# Модули лежат в content, тесты — в assessment; здесь только ссылки и названия для показа.

TEMPLATE_PRIVATE, TEMPLATE_PENDING, TEMPLATE_PUBLISHED, TEMPLATE_REJECTED = "private", "pending", "published", "rejected"
TEMPLATE_REMOVED = "removed"  # снят с платформы администратором


class PlanTemplate(Base):
    """Шаблон КТП: список уроков без дат. Свой, чужой из библиотеки (копия) или публикуемый через модерацию."""

    __tablename__ = "plan_templates"
    __table_args__ = (
        CheckConstraint("status IN ('private', 'pending', 'published', 'rejected', 'removed')", name="status_valid"),
        Index("ix_plan_templates_owner", "owner_id", "updated_at"),
        Index("ix_plan_templates_catalog", "status", "subject"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str | None] = mapped_column(String(80))
    level: Mapped[str | None] = mapped_column(String(40))  # «7 класс», «ОГЭ», «Начинающие»
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), default=TEMPLATE_PRIVATE)
    review_comment: Mapped[str | None] = mapped_column(Text)
    removed_from: Mapped[str | None] = mapped_column(String(10))  # статус до снятия администратором — для отмены
    based_on_id: Mapped[UUID | None]
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    lessons: Mapped[list["TemplateLesson"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="TemplateLesson.position"
    )


class TemplateLesson(Base):
    __tablename__ = "template_lessons"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    template_id: Mapped[UUID] = mapped_column(ForeignKey("plan_templates.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    topic: Mapped[str] = mapped_column(String(300))
    goals: Mapped[str] = mapped_column(Text, default="")  # планируемые результаты
    class_items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    home_items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    exam_item_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid), default=list, server_default="{}")


class Plan(Base):
    """КТП класса, группы или ученика: уроки с датами. Создаётся с нуля, постепенно или из шаблона
    (один шаблон — много привязок, у каждой свои даты)."""

    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("target_type IN ('student', 'group')", name="target_type_valid"),
        Index("ix_plans_teacher", "teacher_id", "updated_at"),
        Index("ix_plans_target", "target_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    teacher_id: Mapped[UUID]
    target_type: Mapped[str] = mapped_column(String(10))
    target_id: Mapped[UUID]
    target_title: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str | None] = mapped_column(String(80))
    template_id: Mapped[UUID | None]
    start_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    lessons: Mapped[list["PlanLesson"]] = relationship(lazy="selectin", cascade="all, delete-orphan", order_by="PlanLesson.position")


class PlanLesson(Base):
    """Урок КТП. Привязывается к занятию в расписании; к одному занятию — несколько уроков КТП (ТЗ)."""

    __tablename__ = "plan_lessons"
    __table_args__ = (Index("ix_plan_lessons_schedule", "schedule_lesson_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    topic: Mapped[str] = mapped_column(String(300))
    goals: Mapped[str] = mapped_column(Text, default="")
    class_items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    home_items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    exam_item_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid), default=list, server_default="{}")
    planned_date: Mapped[date | None] = mapped_column(Date)
    schedule_lesson_id: Mapped[UUID | None]
    done: Mapped[bool] = mapped_column(Boolean, default=False)
