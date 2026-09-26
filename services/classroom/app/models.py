from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, false, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from testmatica_common.ids import uuid7
from testmatica_common.messaging import messaging_tables

LINK_PENDING = "pending"
LINK_ACTIVE = "active"
LINK_DECLINED = "declined"
LINK_ENDED = "ended"

SOURCE_INVITE = "invite"
SOURCE_MANUAL = "manual"
SOURCE_REQUEST = "request"


class Base(DeclarativeBase):
    pass


outbox, inbox = messaging_tables(Base.metadata)


class Person(Base):
    """Реплика публичных данных пользователей из identity (обновляется событиями).
    Нужна, чтобы показывать имена в списках без запросов в identity."""

    __tablename__ = "people"

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    login: Mapped[str | None] = mapped_column(String(64))
    roles: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Group(Base):
    """Школьный класс или учебная группа педагога. Платная или бесплатная — решает педагог (режимов нет)."""

    __tablename__ = "groups"
    __table_args__ = (
        CheckConstraint("kind IN ('class', 'group')", name="kind_valid"),
        Index("ix_groups_teacher", "teacher_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    teacher_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(String(10))
    # Занятия группы платные (оплата — этап 4) или бесплатные (школьный класс, кружок).
    paid: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    title: Mapped[str] = mapped_column(String(120))
    subject: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GroupMember(Base):
    """Состав группы. При исключении строка не удаляется — ставится left_at (история нужна журналу)."""

    __tablename__ = "group_members"
    __table_args__ = (Index("ix_group_members_student", "student_id"),)

    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    student_id: Mapped[UUID] = mapped_column(primary_key=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TeacherStudentLink(Base):
    """Привязка ученика к педагогу. Педагог управляет только привязанными учениками."""

    __tablename__ = "teacher_student_links"
    __table_args__ = (
        UniqueConstraint("teacher_id", "student_id", name="uq_link_teacher_student"),
        CheckConstraint("status IN ('pending', 'active', 'declined', 'ended')", name="status_valid"),
        CheckConstraint("source IN ('invite', 'manual', 'request', 'marketplace')", name="source_valid"),
        Index("ix_links_student", "student_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    teacher_id: Mapped[UUID]
    student_id: Mapped[UUID]
    status: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(12))
    # Индивидуальные занятия с этим учеником платные или бесплатные. Не зависит от групп:
    # ученик школьного класса может отдельно заниматься с тем же учителем платно.
    paid: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Группа, в которую ученик попадёт после подтверждения запроса.
    pending_group_id: Mapped[UUID | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (Index("ix_invitations_teacher", "teacher_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    token: Mapped[str] = mapped_column(String(64), unique=True)
    teacher_id: Mapped[UUID]
    email: Mapped[str] = mapped_column(String(254))
    group_id: Mapped[UUID | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[UUID | None]
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
