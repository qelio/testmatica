from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Uuid,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from testmatica_common.ids import uuid7
from testmatica_common.messaging import messaging_tables

# Уровни учеников и форматы — фильтры поиска (ТЗ, раздел 4).
LEVELS = ("1-4", "5-9", "10-11", "student", "adult")
FORMATS = ("individual", "group")
PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"


class Base(DeclarativeBase):
    pass


outbox, inbox = messaging_tables(Base.metadata)


class Person(Base):
    """Реплика пользователей из identity: имя и роли."""

    __tablename__ = "people"

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    roles: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list)


class TutorProfile(Base):
    """Публичный профиль репетитора. В поиске — только если включён и заполнен (решения №10, №14)."""

    __tablename__ = "tutor_profiles"
    __table_args__ = (
        Index("ix_profiles_subjects", "subject_ids", postgresql_using="gin"),
        Index("ix_profiles_search", "published", "rating"),
    )

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    headline: Mapped[str] = mapped_column(String(150), default="")  # коротко: «Математика ЕГЭ, 10 лет опыта»
    about: Mapped[str] = mapped_column(Text, default="")
    photo_file_id: Mapped[UUID | None]
    subjects: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # [{id, name}] из справочника content
    subject_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid), default=list, server_default="{}")
    levels: Mapped[list[str]] = mapped_column(ARRAY(String(10)), default=list, server_default="{}")
    formats: Mapped[list[str]] = mapped_column(ARRAY(String(12)), default=list, server_default="{}")
    # Ориентировочная цена за 60 минут: итоговую предлагает ученик и договариваются в чате (ТЗ, раздел 4).
    price: Mapped[int | None] = mapped_column(Integer)
    experience_years: Mapped[int | None] = mapped_column(SmallInteger)
    # Считаются по одобренным отзывам (шаг 4.3) и документам об образовании.
    rating: Mapped[float | None] = mapped_column(Float)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    education_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EducationDoc(Base):
    """Карточка документа об образовании: проверяет модератор; публично — только бейдж (ТЗ, раздел 3)."""

    __tablename__ = "education_docs"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="status_valid"),
        Index("ix_education_user", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String(200))  # «Диплом учителя математики», «Курс ...»
    institution: Mapped[str] = mapped_column(String(200))
    year: Mapped[int] = mapped_column(SmallInteger)
    file_id: Mapped[UUID]
    filename: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), default=PENDING)
    comment: Mapped[str | None] = mapped_column(Text)  # чего не хватает — при отклонении
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------- заявки (шаг 4.2) ----------

GOALS = ("ege", "oge", "school", "gaps", "olympiad", "other")
REQUEST_OPEN, REQUEST_AGREED, REQUEST_CLOSED, REQUEST_EXPIRED = "open", "agreed", "closed", "expired"
RESPONSE_ACTIVE, RESPONSE_AGREED, RESPONSE_CLOSED = "active", "agreed", "closed"


class Competency(Base):
    """Справочник компетенций по предмету («Дроби», «Производная») — ведут модераторы (ТЗ, раздел 4)."""

    __tablename__ = "competencies"
    __table_args__ = (Index("ix_competencies_subject", "subject_id", "position"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    subject_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer, default=0)


class LessonRequest(Base):
    """Заявка ученика: адресная («Хочу с вами заниматься») или открытая — её видят репетиторы по предмету."""

    __tablename__ = "requests"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'agreed', 'closed', 'expired')", name="status_valid"),
        CheckConstraint("duration_min IN (30, 45, 60, 90)", name="duration_valid"),
        Index("ix_requests_open", "status", "subject_id", "created_at"),
        Index("ix_requests_student", "student_id", "created_at"),
        Index("ix_requests_tutor", "tutor_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    student_id: Mapped[UUID]
    tutor_id: Mapped[UUID | None]  # None — открытая заявка
    subject_id: Mapped[UUID]
    subject_name: Mapped[str] = mapped_column(String(80))
    goal: Mapped[str] = mapped_column(String(10))
    current_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid), default=list, server_default="{}")  # что уже знаю
    desired_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid), default=list, server_default="{}")  # что хочу получить
    # {"weekdays": [0..6]} — удобные дни; время согласуют в чате
    schedule: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    price: Mapped[int] = mapped_column(Integer)  # предлагает ученик (ТЗ: репетитор цену заранее не устанавливает)
    duration_min: Mapped[int] = mapped_column(SmallInteger)
    comment: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), default=REQUEST_OPEN)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Response(Base):
    """Переговоры репетитора и ученика по заявке. Id отклика — это и id чата переговоров в сервисе chat."""

    __tablename__ = "responses"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'agreed', 'closed')", name="status_valid"),
        CheckConstraint("proposed_by IN ('student', 'tutor')", name="proposed_by_valid"),
        Index("uq_responses_request_tutor", "request_id", "tutor_id", unique=True),
        Index("ix_responses_tutor", "tutor_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    request_id: Mapped[UUID] = mapped_column(ForeignKey("requests.id", ondelete="CASCADE"))
    tutor_id: Mapped[UUID]
    status: Mapped[str] = mapped_column(String(10), default=RESPONSE_ACTIVE)
    # Текущее предложение цены и чьё оно: «Договорились» принимает предложение другой стороны.
    price: Mapped[int] = mapped_column(Integer)
    proposed_by: Mapped[str] = mapped_column(String(8))
    message: Mapped[str] = mapped_column(Text, default="")
    agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
