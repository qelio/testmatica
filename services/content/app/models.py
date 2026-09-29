from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, false, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from testmatica_common.ids import uuid7
from testmatica_common.messaging import messaging_tables

# Статусы курса. Разделы и модули наследуют статус своего курса.
PRIVATE = "private"  # приватная библиотека педагога: видна ему и привязанным ученикам
PENDING = "pending"  # на модерации — изменения заблокированы
PUBLISHED = "published"  # публичная библиотека: видна всем, включая гостей
REJECTED = "rejected"  # отклонён модератором — можно исправить и отправить снова
REMOVED = "removed"  # снят с платформы администратором: виден только автору (с причиной) и модераторам

KINDS = ("course", "section", "module")
CHILD_KIND = {"course": "section", "section": "module"}

# task — задача из банка заданий (только с автопроверкой), решается прямо в модуле.
MATERIAL_KINDS = ("text", "card", "video", "pdf", "file", "link", "task")
FILE_KINDS = ("video", "pdf", "file")

DEFAULT_SUBJECTS = (
    "Математика", "Алгебра", "Геометрия", "Информатика", "Физика", "Химия", "Биология", "География",
    "История", "Обществознание", "Русский язык", "Литература", "Английский язык",
)


class Base(DeclarativeBase):
    pass


outbox, inbox = messaging_tables(Base.metadata)


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    # Справочник ведут модераторы. Удалять нельзя (на предмет ссылаются курсы, задачи, профили) — только скрыть из выбора.
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class Person(Base):
    """Реплика имён из identity — автор курса в публичной библиотеке, ученики в отчёте о прогрессе."""

    __tablename__ = "people"

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))


class RelLink(Base):
    """Активные привязки педагог–ученик (реплика classroom): ученики видят приватную библиотеку своих педагогов."""

    __tablename__ = "rel_links"
    __table_args__ = (Index("ix_content_rel_links_student", "student_id"),)

    teacher_id: Mapped[UUID] = mapped_column(primary_key=True)
    student_id: Mapped[UUID] = mapped_column(primary_key=True)


class Node(Base):
    """Курс, раздел или модуль. course_id у всех узлов указывает на корень — удобно выбирать поддерево."""

    __tablename__ = "nodes"
    __table_args__ = (
        CheckConstraint("kind IN ('course', 'section', 'module')", name="kind_valid"),
        CheckConstraint("status IS NULL OR status IN ('private', 'pending', 'published', 'rejected', 'removed')", name="status_valid"),
        CheckConstraint("(kind = 'course') = (parent_id IS NULL)", name="only_course_is_root"),
        Index("ix_nodes_course", "course_id"),
        Index("ix_nodes_owner", "owner_id"),
        Index("ix_nodes_catalog", "status", "subject_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    kind: Mapped[str] = mapped_column(String(10))
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    course_id: Mapped[UUID]
    subject_id: Mapped[UUID | None] = mapped_column(ForeignKey("subjects.id"))
    owner_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    # Только у курса:
    status: Mapped[str | None] = mapped_column(String(10))
    review_comment: Mapped[str | None] = mapped_column(Text)
    removed_from: Mapped[str | None] = mapped_column(String(10))  # статус до снятия администратором — для отмены
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (
        CheckConstraint("kind IN ('text', 'card', 'video', 'pdf', 'file', 'link', 'task')", name="kind_valid"),
        Index("ix_materials_module", "module_id", "position"),
        Index("ix_materials_course", "course_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    module_id: Mapped[UUID] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    course_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(200))
    # Текст и теоркарточки — Markdown с формулами ($…$, $$…$$).
    body: Mapped[str] = mapped_column(Text, default="")
    file_id: Mapped[UUID | None]
    file_name: Mapped[str | None] = mapped_column(String(200))
    file_mime: Mapped[str | None] = mapped_column(String(120))
    file_size: Mapped[int | None]
    url: Mapped[str | None] = mapped_column(String(500))
    task_id: Mapped[UUID | None]  # для kind = task
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MaterialProgress(Base):
    """Что ученик открыл и где остановился в видео."""

    __tablename__ = "material_progress"
    __table_args__ = (Index("ix_progress_course_user", "course_id", "user_id"),)

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    material_id: Mapped[UUID] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True)
    course_id: Mapped[UUID]
    position_sec: Mapped[int] = mapped_column(Integer, default=0)
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Favorite(Base):
    __tablename__ = "favorites"

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    material_id: Mapped[UUID] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------- главная страница и новости (редактирует администратор) ----------

NEWS_DRAFT, NEWS_PUBLISHED = "draft", "published"


class SiteSetting(Base):
    """Содержимое сайта: key = landing — разделы главной (схема — site.Landing)."""

    __tablename__ = "site_settings"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_by: Mapped[UUID | None]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class News(Base):
    """Новость на сайте: черновик виден только администраторам, опубликованная — всем."""

    __tablename__ = "news"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published')", name="status_valid"),
        Index("ix_news_published", "status", "published_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    slug: Mapped[str] = mapped_column(String(120), unique=True)  # адрес: /news/<slug>
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text, default="")  # Markdown
    cover_file_id: Mapped[UUID | None]
    status: Mapped[str] = mapped_column(String(10), default=NEWS_DRAFT)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author_id: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
