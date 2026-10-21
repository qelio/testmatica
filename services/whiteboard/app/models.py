"""Доски (решение №60): к занятию или свободные. Объекты доски — штрихи, фигуры, текст, картинки, формулы."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, Uuid, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from testmatica_common.ids import uuid7
from testmatica_common.messaging import messaging_tables

# Доступ учеников: не видят / только смотрят / тоже рисуют.
ACCESS_NONE, ACCESS_READ, ACCESS_EDIT = "none", "read", "edit"
PAPER_STYLES = ("plain", "lines_narrow", "lines", "lines_wide", "grid_small", "grid", "grid_big", "dots")
PAPER_COLORS = ("white", "cream", "yellow", "blue", "green", "pink", "gray", "chalk")
KINDS = ("stroke", "shape", "text", "image", "formula")


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


class Board(Base):
    __tablename__ = "boards"
    __table_args__ = (
        CheckConstraint("access IN ('none', 'read', 'edit')", name="access_valid"),
        Index("ix_boards_owner", "owner_id", "updated_at"),
        Index("ix_boards_members", "member_ids", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String(200))
    # Доска занятия — одна на занятие (у группового — общая на класс).
    lesson_id: Mapped[UUID | None] = mapped_column(unique=True)
    lesson_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Кому видна: класс (группа) или ученик — у занятия как у занятия, у свободной доски — по выбору педагога.
    group_id: Mapped[UUID | None]
    student_id: Mapped[UUID | None]
    target_title: Mapped[str | None] = mapped_column(String(200))
    # Ученики, которым доска видна (состав занятия, класса); обновляется, когда педагог открывает доску.
    member_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid), default=list, server_default="{}")
    access: Mapped[str] = mapped_column(String(4), default=ACCESS_READ, server_default=ACCESS_READ)
    paper_style: Mapped[str] = mapped_column(String(12), default="plain", server_default="plain")
    paper_color: Mapped[str] = mapped_column(String(8), default="white", server_default="white")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Item(Base):
    """Объект доски. id задаёт клиент — так правки приходят от всех участников без ожидания сервера;
    при одновременной правке одного объекта остаётся последняя."""

    __tablename__ = "items"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    board_id: Mapped[UUID] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    z: Mapped[float] = mapped_column(Float, default=0)  # порядок наложения
    author_id: Mapped[UUID]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
