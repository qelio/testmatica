"""Подписка педагога: тариф, оплата, автопродление, история платежей."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError
from testmatica_common.internal import internal_guard

from .. import subscriptions
from ..config import settings
from ..deps import auth, db
from ..models import PAYMENT_PENDING, Payment, Subscription
from ..providers import FakeProvider, get_provider
from ..schemas import AutoRenewIn, CheckoutIn, FakeResultIn, PaymentOut, PlansIn, SubscriptionOut

router = APIRouter(tags=["subscription"])
internal = APIRouter(prefix="/internal", dependencies=[Depends(internal_guard(settings.internal_token))], tags=["internal"])
teacher = auth.require(ROLE_TEACHER)

PENDING_TTL = timedelta(minutes=30)  # незавершённый платёж можно продолжить, потом создаётся новый


def payment_out(p: Payment) -> PaymentOut:
    return PaymentOut(id=p.id, purpose=p.purpose, description=p.description, amount_rub=p.amount_kop / 100, status=p.status,
                      recurring=p.recurring, confirmation_url=p.confirmation_url if p.status == PAYMENT_PENDING else None,
                      error=p.error, created_at=p.created_at, paid_at=p.paid_at)


async def _pending(session: AsyncSession, user_id: UUID) -> Payment | None:
    return await session.scalar(
        select(Payment).where(Payment.user_id == user_id, Payment.status == PAYMENT_PENDING, Payment.recurring.is_(False),
                              Payment.created_at > datetime.now(UTC) - PENDING_TTL)
        .order_by(Payment.created_at.desc()).limit(1)
    )


async def _state(session: AsyncSession, user_id: UUID) -> SubscriptionOut:
    sub = await session.get(Subscription, user_id)
    pending = await _pending(session, user_id)
    return SubscriptionOut(
        plan=subscriptions.plan_of(sub), period_end=sub.period_end if sub else None, auto_renew=bool(sub and sub.auto_renew),
        payment_method_title=sub.payment_method_title if sub else None, price_rub=settings.basic_price_rub,
        pending_payment=payment_out(pending) if pending else None,
    )


@router.get("/subscription", response_model=SubscriptionOut)
async def my_subscription(principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> SubscriptionOut:
    return await _state(session, principal.user_id)


@router.post("/subscription/checkout", response_model=PaymentOut, status_code=201)
async def checkout(body: CheckoutIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> PaymentOut:
    """Оплатить месяц «Базового» (или продлить досрочно): платёж у провайдера и ссылка на страницу оплаты."""
    pending = await _pending(session, principal.user_id)
    if pending is not None and pending.save_method == body.auto_renew:
        return payment_out(pending)
    if pending is not None:  # передумали насчёт автопродления — старый платёж отменяем
        pending.status, pending.error = "canceled", "Заменён новым платежом"
    payment = subscriptions.new_payment(principal.user_id, recurring=False, save_method=body.auto_renew)
    session.add(payment)
    await session.flush()
    created = await get_provider().create(payment)
    payment.provider_payment_id, payment.confirmation_url = created.provider_payment_id, created.confirmation_url
    await session.commit()
    return payment_out(payment)


@router.put("/subscription/auto-renew", response_model=SubscriptionOut)
async def set_auto_renew(body: AutoRenewIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> SubscriptionOut:
    sub = await session.get(Subscription, principal.user_id, with_for_update=True)
    if sub is None or subscriptions.plan_of(sub) != subscriptions.BASIC:
        raise ApiError(409, "no_subscription", "Сначала подключите тариф «Базовый»")
    if body.enabled and not sub.payment_method_id:
        raise ApiError(409, "no_payment_method", "Нет сохранённого способа оплаты — продлите подписку с галочкой «Продлевать автоматически»")
    if sub.auto_renew != body.enabled:
        sub.auto_renew, sub.renew_failures, sub.reminded_at = body.enabled, 0, None
        await subscriptions.changed(session, sub, "auto_renew_on" if body.enabled else "auto_renew_off")
    await session.commit()
    return await _state(session, principal.user_id)


@router.delete("/subscription/payment-method", response_model=SubscriptionOut)
async def forget_method(principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> SubscriptionOut:
    """Отвязать карту: автопродление выключается, оплаченный период остаётся."""
    sub = await session.get(Subscription, principal.user_id, with_for_update=True)
    if sub is not None and sub.payment_method_id:
        was = sub.auto_renew
        sub.payment_method_id = sub.payment_method_title = None
        sub.auto_renew = False
        if was:
            await subscriptions.changed(session, sub, "auto_renew_off")
    await session.commit()
    return await _state(session, principal.user_id)


@router.get("/payments", response_model=list[PaymentOut])
async def my_payments(principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> list[PaymentOut]:
    rows = (await session.execute(
        select(Payment).where(Payment.user_id == principal.user_id).order_by(Payment.created_at.desc()).limit(100)
    )).scalars()
    return [payment_out(p) for p in rows]


async def _own_payment(session: AsyncSession, payment_id: UUID, principal: Principal, lock: bool = False) -> Payment:
    p = await session.get(Payment, payment_id, with_for_update=lock)
    if p is None or p.user_id != principal.user_id:
        raise ApiError(404, "payment_not_found", "Платёж не найден")
    return p


@router.get("/payments/{payment_id}", response_model=PaymentOut)
async def payment(payment_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> PaymentOut:
    return payment_out(await _own_payment(session, payment_id, principal))


@router.post("/fake-provider/payments/{payment_id}", response_model=PaymentOut)
async def fake_result(
    payment_id: UUID, body: FakeResultIn, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> PaymentOut:
    """Тестовая страница оплаты сообщает результат — так же, как настоящий провайдер присылал бы уведомление."""
    if settings.payment_provider != FakeProvider.name:
        raise ApiError(404, "not_found", "Не найдено")
    p = await _own_payment(session, payment_id, principal, lock=True)
    if p.provider != FakeProvider.name:
        raise ApiError(404, "payment_not_found", "Платёж не найден")
    if p.status != PAYMENT_PENDING:
        raise ApiError(409, "payment_finished", "Платёж уже завершён")
    if body.outcome == "cancel":
        await subscriptions.payment_failed(session, p, "Оплата отменена")
    elif body.card_last4 == FakeProvider.DECLINED_SUFFIX:
        await subscriptions.payment_failed(session, p, "Банк отклонил оплату")
    else:
        await subscriptions.payment_succeeded(session, p, f"fake_card_{body.card_last4}", f"Карта •• {body.card_last4}")
    await session.commit()
    return payment_out(p)


@internal.post("/plans", response_model=dict[str, str])
async def plans(body: PlansIn, session: AsyncSession = Depends(db.session)) -> dict[str, str]:
    """Тариф педагогов для проверки лимитов в других сервисах: free / basic."""
    if not body.user_ids:
        return {}
    subs = {s.user_id: s for s in (await session.execute(select(Subscription).where(Subscription.user_id.in_(body.user_ids)))).scalars()}
    now = datetime.now(UTC)
    return {str(u): subscriptions.plan_of(subs.get(u), now) for u in body.user_ids}
