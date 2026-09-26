from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, SmallInteger, String, false, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from testmatica_common.ids import uuid7
from testmatica_common.messaging import messaging_tables

PAYMENT_PENDING, PAYMENT_SUCCEEDED, PAYMENT_CANCELED = "pending", "succeeded", "canceled"


class Base(DeclarativeBase):
    pass


outbox, inbox = messaging_tables(Base.metadata)


class Subscription(Base):
    """Подписка педагога (ТЗ, раздел 12). Тариф «Базовый» действует до period_end; после — бесплатный."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("plan IN ('basic')", name="plan_valid"),
        Index("ix_subscriptions_period_end", "period_end"),
    )

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    plan: Mapped[str] = mapped_column(String(10), default="basic")
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Сохранённый способ оплаты у провайдера — для автопродления (сами реквизиты у нас не хранятся).
    payment_method_id: Mapped[str | None] = mapped_column(String(100))
    payment_method_title: Mapped[str | None] = mapped_column(String(100))  # «Карта •• 4242»
    renew_failures: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # напоминание о конце периода
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # когда вернулся бесплатный тариф
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Payment(Base):
    """Платёж через провайдера. Пока только за подписку; оплата занятий — позже (этап 4.4)."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'succeeded', 'canceled')", name="status_valid"),
        CheckConstraint("purpose IN ('subscription')", name="purpose_valid"),
        CheckConstraint("amount_kop > 0", name="amount_positive"),
        Index("ix_payments_user", "user_id", "created_at"),
        Index("uq_payments_provider", "provider", "provider_payment_id", unique=True,
              postgresql_where=text("provider_payment_id IS NOT NULL")),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID]
    purpose: Mapped[str] = mapped_column(String(20), default="subscription")
    plan: Mapped[str] = mapped_column(String(10), default="basic")
    amount_kop: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), default=PAYMENT_PENDING)
    provider: Mapped[str] = mapped_column(String(20))
    provider_payment_id: Mapped[str | None] = mapped_column(String(100))
    confirmation_url: Mapped[str | None] = mapped_column(String(500))
    recurring: Mapped[bool] = mapped_column(Boolean, default=False)  # автопродление сохранённым способом
    save_method: Mapped[bool] = mapped_column(Boolean, default=False)  # включить автопродление после оплаты
    error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformSetting(Base):
    """Настройки платформы, которые меняет администратор (ТЗ: «тарифы, лимиты free-версии, параметры escrow»).
    Нет строки — действует значение по умолчанию из testmatica_common.plans.PLATFORM_DEFAULTS."""

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[int] = mapped_column(Integer)
    updated_by: Mapped[UUID | None]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
