"""Подписка: действие оплаты, автопродление, окончание периода."""

import calendar
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .deps import db, outbox
from .models import PAYMENT_CANCELED, PAYMENT_PENDING, PAYMENT_SUCCEEDED, Payment, Subscription
from .providers import get_provider

log = logging.getLogger(__name__)

FREE, BASIC = "free", "basic"


def add_month(dt: datetime) -> datetime:
    """Тот же день следующего месяца (31 января → 28/29 февраля)."""
    year, month = (dt.year + 1, 1) if dt.month == 12 else (dt.year, dt.month + 1)
    return dt.replace(year=year, month=month, day=min(dt.day, calendar.monthrange(year, month)[1]))


def plan_of(sub: Subscription | None, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return BASIC if sub is not None and sub.period_end > now else FREE


def price_kop() -> int:
    return settings.basic_price_rub * 100


async def changed(session: AsyncSession, sub: Subscription, reason: str) -> None:
    """Тариф изменился или продлён — сервисы с лимитами и уведомления узнают из события."""
    await outbox.event(session, "billing.subscription.changed", {
        "user_id": str(sub.user_id), "plan": plan_of(sub), "period_end": sub.period_end.isoformat(), "reason": reason,
        "auto_renew": sub.auto_renew,
    }, actor_id=sub.user_id if reason == "purchased" else None)


async def payment_succeeded(session: AsyncSession, payment: Payment, method_id: str | None, method_title: str | None) -> None:
    """Оплата прошла: продлить (или начать) период на месяц. Повторное уведомление провайдера — без эффекта."""
    if payment.status != PAYMENT_PENDING:
        return
    now = datetime.now(UTC)
    payment.status, payment.paid_at = PAYMENT_SUCCEEDED, now
    sub = await session.get(Subscription, payment.user_id, with_for_update=True)
    if sub is None:
        sub = Subscription(user_id=payment.user_id, plan=BASIC, period_start=now, period_end=now, auto_renew=False)
        session.add(sub)
    start = max(now, sub.period_end)  # досрочная оплата продлевает от конца текущего периода
    if sub.period_end <= now:
        sub.period_start = now
    sub.period_end = add_month(start)
    sub.renew_failures, sub.reminded_at, sub.expired_at = 0, None, None
    if payment.save_method and method_id:
        sub.payment_method_id, sub.payment_method_title, sub.auto_renew = method_id, method_title, True
    await session.flush()
    await outbox.event(session, "billing.payment.succeeded", {
        "payment_id": str(payment.id), "user_id": str(payment.user_id), "amount_kop": payment.amount_kop,
        "purpose": payment.purpose, "recurring": payment.recurring,
    }, actor_id=None if payment.recurring else payment.user_id)
    await changed(session, sub, "renewed" if payment.recurring else "purchased")


async def payment_failed(session: AsyncSession, payment: Payment, error: str | None) -> None:
    if payment.status != PAYMENT_PENDING:
        return
    payment.status, payment.error = PAYMENT_CANCELED, (error or "Оплата не прошла")[:300]
    await outbox.event(session, "billing.payment.failed", {
        "payment_id": str(payment.id), "user_id": str(payment.user_id), "purpose": payment.purpose,
        "recurring": payment.recurring, "error": payment.error,
    }, actor_id=None if payment.recurring else payment.user_id)


def new_payment(user_id: UUID, *, recurring: bool, save_method: bool) -> Payment:
    return Payment(
        user_id=user_id, purpose="subscription", plan=BASIC, amount_kop=price_kop(), provider=get_provider().name,
        description="Подписка «Базовый» на 1 месяц" + (" (автопродление)" if recurring else ""),
        recurring=recurring, save_method=save_method, status=PAYMENT_PENDING,
    )


async def renew(session: AsyncSession, sub: Subscription) -> None:
    """Автопродление сохранённым способом. После трёх неудач подряд автопродление выключается."""
    payment = new_payment(sub.user_id, recurring=True, save_method=False)
    session.add(payment)
    await session.flush()
    result = await get_provider().charge(payment, sub.payment_method_id or "")
    payment.provider_payment_id = result.provider_payment_id
    if result.succeeded:
        await payment_succeeded(session, payment, None, None)
        return
    await payment_failed(session, payment, result.error)
    sub.renew_failures += 1
    if sub.renew_failures >= 3:
        sub.auto_renew = False


async def tick() -> None:
    """Фоновая задача: автопродление, напоминание о конце периода, возврат на бесплатный тариф."""
    now = datetime.now(UTC)
    async with db.sessionmaker() as session, session.begin():
        due = (await session.execute(
            select(Subscription)
            .where(Subscription.period_end > now - timedelta(days=3),  # после конца ещё пару дней пробуем продлить
                   Subscription.period_end <= now + timedelta(hours=settings.renew_before_hours),
                   Subscription.auto_renew.is_(True), Subscription.payment_method_id.is_not(None))
            .with_for_update(skip_locked=True)
        )).scalars().all()
        for sub in due:
            # Не чаще раза в 6 часов после неудачи.
            last = await session.scalar(
                select(Payment.created_at).where(Payment.user_id == sub.user_id, Payment.recurring.is_(True))
                .order_by(Payment.created_at.desc()).limit(1)
            )
            if last is None or last < now - timedelta(hours=6):
                await renew(session, sub)

        remind = (await session.execute(
            select(Subscription)
            .where(Subscription.period_end > now, Subscription.period_end <= now + timedelta(days=settings.remind_before_days),
                   Subscription.auto_renew.is_(False), Subscription.reminded_at.is_(None))
            .with_for_update(skip_locked=True)
        )).scalars().all()
        for sub in remind:
            sub.reminded_at = now
            await outbox.event(session, "billing.subscription.expiring", {
                "user_id": str(sub.user_id), "period_end": sub.period_end.isoformat()})

        ended = (await session.execute(
            select(Subscription).where(Subscription.period_end <= now, Subscription.expired_at.is_(None))
            .with_for_update(skip_locked=True)
        )).scalars().all()
        for sub in ended:
            sub.expired_at = now
            await changed(session, sub, "expired")
