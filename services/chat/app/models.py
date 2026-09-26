from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, false, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from testmatica_common.ids import uuid7
from testmatica_common.messaging import messaging_tables

KIND_DIRECT = "direct"
KIND_GROUP = "group"
KIND_DEAL = "deal"  # чат переговоров по заявке (id = id отклика в marketplace)


class Base(DeclarativeBase):
    pass


outbox, inbox = messaging_tables(Base.metadata)


# ---------- реплики из identity и classroom ----------


class Person(Base):
    __tablename__ = "people"

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    login: Mapped[str | None] = mapped_column(String(64))
    roles: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RelLink(Base):
    """Активные привязки педагог–ученик (реплика classroom)."""

    __tablename__ = "rel_links"
    __table_args__ = (Index("ix_rel_links_student", "student_id"),)

    teacher_id: Mapped[UUID] = mapped_column(primary_key=True)
    student_id: Mapped[UUID] = mapped_column(primary_key=True)


class RelGroup(Base):
    __tablename__ = "rel_groups"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    teacher_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String(120))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class RelGroupMember(Base):
    __tablename__ = "rel_group_members"
    __table_args__ = (Index("ix_rel_members_student", "student_id"),)

    group_id: Mapped[UUID] = mapped_column(primary_key=True)
    student_id: Mapped[UUID] = mapped_column(primary_key=True)


# ---------- чаты ----------


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("kind IN ('direct', 'group', 'deal')", name="kind_valid"),
        CheckConstraint(
            "(kind = 'group' AND group_id IS NOT NULL) OR (kind = 'direct' AND pair_key IS NOT NULL) OR kind = 'deal'",
            name="ref_valid",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    kind: Mapped[str] = mapped_column(String(10))
    # Групповой чат — один на группу; личный — один на пару пользователей ("меньший_id:больший_id").
    group_id: Mapped[UUID | None] = mapped_column(unique=True)
    pair_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    title: Mapped[str | None] = mapped_column(String(200))  # для чатов переговоров: «Заявка: Математика»
    pinned_message_id: Mapped[UUID | None]
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationMember(Base):
    __tablename__ = "conversation_members"
    __table_args__ = (Index("ix_members_user", "user_id", postgresql_where=text("left_at IS NULL")),)

    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    # teacher — может писать объявления в групповом чате.
    role: Mapped[str] = mapped_column(String(10), default="member")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    """Сообщения хранятся бессрочно (ТЗ, раздел 11). Удаление — мягкое."""

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    author_id: Mapped[UUID]
    text: Mapped[str] = mapped_column(Text)
    # [{"id", "filename", "mime", "size"}] — сами файлы в сервисе media.
    attachments: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default="[]")
    is_announcement: Mapped[bool] = mapped_column(Boolean, default=False)
    # Служебное сообщение переговоров: предложена цена, «Договорились», заявка закрыта.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
