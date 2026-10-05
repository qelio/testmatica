from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, false, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from testmatica_common.ids import uuid7
from testmatica_common.messaging import messaging_tables
from testmatica_common.names import PersonName

STATUS_PENDING = "pending_verification"
STATUS_ACTIVE = "active"
STATUS_BANNED = "banned"
STATUS_DELETED = "deleted"

ROLES = ("student", "teacher", "moderator", "admin")



class Base(DeclarativeBase):
    pass


outbox, inbox = messaging_tables(Base.metadata)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            f"status IN ('{STATUS_PENDING}', '{STATUS_ACTIVE}', '{STATUS_BANNED}', '{STATUS_DELETED}')",
            name="status_valid",
        ),
        CheckConstraint("two_factor_method IN ('email', 'phone')", name="two_factor_method_valid"),
        CheckConstraint("email IS NOT NULL OR login IS NOT NULL", name="has_identifier"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    # email и login хранятся в нижнем регистре.
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    login: Mapped[str | None] = mapped_column(String(64), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))
    # Имя по частям (решение №35); full_name — «Фамилия Имя Отчество», собирается из них (set_name) и расходится
    # по репликам других сервисов, поэтому везде показывается и сортируется по фамилии.
    last_name: Mapped[str] = mapped_column(String(80), default="", server_default="")
    first_name: Mapped[str] = mapped_column(String(80), default="", server_default="")
    middle_name: Mapped[str] = mapped_column(String(80), default="", server_default="")
    full_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default=STATUS_PENDING)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # None — 2FA не настроена (только аккаунты, созданные педагогом без email и телефона).
    two_factor_method: Mapped[str | None] = mapped_column(String(10))
    managed_by_teacher_id: Mapped[UUID | None]
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    avatar_file_id: Mapped[UUID | None]  # фото в media (purpose avatar)
    # Блокировка и удаление администратором. Удалённый аккаунт 30 дней можно восстановить, затем он обезличивается (решение №9).
    status_reason: Mapped[str | None] = mapped_column(String(500))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list["UserRole"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", back_populates="user"
    )

    @property
    def role_names(self) -> list[str]:
        return sorted(r.role for r in self.roles)

    def set_name(self, name: PersonName) -> bool:
        """Задать имя; True — если что-то изменилось."""
        before = (self.last_name, self.first_name, self.middle_name, self.full_name)
        self.last_name, self.first_name, self.middle_name = name.last_name, name.first_name, name.middle_name
        self.full_name = name.full_name
        return before != (self.last_name, self.first_name, self.middle_name, self.full_name)


class UserActivity(Base):
    """День, когда пользователь был на платформе (вход или продление сессии) — для DAU/MAU."""

    __tablename__ = "user_activity"
    __table_args__ = (Index("ix_user_activity_day", "day"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        CheckConstraint("role IN ('student', 'teacher', 'moderator', 'admin')", name="role_valid"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="roles")


class OtpChallenge(Base):
    """Одноразовый код: подтверждение email, второй фактор при входе, сброс пароля."""

    __tablename__ = "otp_challenges"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(32))
    code_hash: Mapped[str] = mapped_column(String(64))
    destination: Mapped[str] = mapped_column(String(254))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    """Refresh-токены хранятся только в виде хэша. family_id объединяет цепочку ротаций:
    повторное использование старого токена отзывает всю цепочку (признак кражи)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    family_id: Mapped[UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # rotated — заменён новым при /refresh; logout, password_reset, reuse — отозван.
    revoke_reason: Mapped[str | None] = mapped_column(String(20))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Consent(Base):
    """Согласия пользователя (152-ФЗ): тип, версия документа, время, IP и браузер — чтобы подтвердить факт согласия."""

    __tablename__ = "consents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    version: Mapped[str] = mapped_column(String(20))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    # registration — при регистрации; first_login — окно при входе (ученик, созданный педагогом, или новая редакция)
    source: Mapped[str] = mapped_column(String(20), default="registration", server_default="registration")
    # Кто подтвердил: сам пользователь 14+ или родитель (законный представитель) — для учеников.
    by_representative: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApiKey(Base):
    """Личный ключ доступа (решение №41): подключение Claude (MCP) и других программ от имени пользователя.
    Хранится только хеш; сам ключ показывается один раз при выпуске."""

    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_api_keys_user", "user_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    prefix: Mapped[str] = mapped_column(String(12))  # «tm_ab12cd34» — чтобы узнать ключ в списке
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
