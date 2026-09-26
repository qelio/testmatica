"""Админ-панель: настройки платформы, платежи и выручка, ручное продление подписки."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_ADMIN, Principal
from testmatica_common.errors import ApiError
from testmatica_common.plans import PLATFORM_DEFAULTS

from .. import subscriptions
from ..deps import auth, db, outbox
from ..models import PAYMENT_SUCCEEDED, Payment, PlatformSetting, Subscription
from ..schemas import PaymentOut
from .subscription import payment_out

router = APIRouter(prefix="/admin", tags=["admin"])
admin = auth.require(ROLE_ADMIN)

# Пределы значений: защита от опечаток вроде цены 0 или лимита в 10 000 групп.
LIMITS = {
    "basic_price_rub": (0, 100_000),
    "free_max_groups": (1, 100),
    "free_video_minutes": (10, 300),
    "free_recordings_keep": (0, 100),
    "free_recording_days": (1, 365),
    "basic_recording_days": (1, 365),
    "commission_percent": (0, 50),
    "dispute_window_minutes": (0, 1440),
    "payment_deadline_hours": (0, 72),
    "payout_min_rub": (0, 1_000_000),
}


class SettingsIn(BaseModel):
    values: dict[str, int] = Field(min_length=1)


class AdminPayment(PaymentOut):
    user_id: UUID
    provider: str


class MonthPoint(BaseModel):
    month: date
    revenue_rub: float
    payments: int


class BillingStats(BaseModel):
    subscribers: int = Field(description="Сейчас на «Базовом»")
    auto_renew: int
    ever_paid: int = Field(description="Педагогов, хоть раз оплативших")
    revenue_rub: float = Field(description="Всего оплачено")
    months: list[MonthPoint]


class GrantIn(BaseModel):
    days: int = Field(ge=1, le=366)
    reason: str = Field(min_length=3, max_length=500)


@router.get("/settings", response_model=dict[str, int])
async def get_settings(_: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> dict[str, int]:
    return await subscriptions.platform_settings(session)


@router.put("/settings", response_model=dict[str, int])
async def put_settings(body: SettingsIn, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> dict[str, int]:
    """Поменять настройки. Сервисы с лимитами подхватывают их в течение 30 секунд."""
    current = await subscriptions.platform_settings(session)
    changes = {}
    for key, value in body.values.items():
        if key not in PLATFORM_DEFAULTS:
            raise ApiError(422, "unknown_setting", f"Неизвестная настройка: {key}")
        lo, hi = LIMITS[key]
        if not lo <= value <= hi:
            raise ApiError(422, "setting_out_of_range", f"{key}: допустимо от {lo} до {hi}", {"key": key})
        if current[key] != value:
            changes[key] = {"from": current[key], "to": value}
            row = await session.get(PlatformSetting, key, with_for_update=True)
            if row is None:
                session.add(PlatformSetting(key=key, value=value, updated_by=principal.user_id))
            else:
                row.value, row.updated_by = value, principal.user_id
    if changes:
        await outbox.event(session, "billing.settings.updated", {"changes": changes}, actor_id=principal.user_id)
        await session.commit()
    return await subscriptions.platform_settings(session)


@router.get("/payments", response_model=list[AdminPayment])
async def payments(
    status: str | None = Query(None, pattern="^(pending|succeeded|canceled)$"),
    user_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: Principal = Depends(admin),
    session: AsyncSession = Depends(db.session),
) -> list[AdminPayment]:
    query = select(Payment)
    if status:
        query = query.where(Payment.status == status)
    if user_id:
        query = query.where(Payment.user_id == user_id)
    rows = (await session.execute(query.order_by(Payment.created_at.desc()).limit(limit).offset(offset))).scalars()
    return [AdminPayment(**payment_out(p).model_dump(), user_id=p.user_id, provider=p.provider) for p in rows]


@router.get("/stats", response_model=BillingStats)
async def stats(_: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> BillingStats:
    now = datetime.now(UTC)
    subscribers = await session.scalar(select(func.count()).select_from(Subscription).where(Subscription.period_end > now)) or 0
    auto = await session.scalar(select(func.count()).select_from(Subscription).where(
        Subscription.period_end > now, Subscription.auto_renew.is_(True))) or 0
    paid = Payment.status == PAYMENT_SUCCEEDED
    ever = await session.scalar(select(func.count(func.distinct(Payment.user_id))).where(paid)) or 0
    total = await session.scalar(select(func.coalesce(func.sum(Payment.amount_kop), 0)).where(paid)) or 0
    month = func.date_trunc("month", func.timezone("UTC", Payment.paid_at))
    since = (now.replace(day=1) - timedelta(days=335)).replace(day=1)
    rows = (await session.execute(
        select(month, func.sum(Payment.amount_kop), func.count()).where(paid, Payment.paid_at >= since).group_by(month).order_by(month)
    )).all()
    return BillingStats(subscribers=subscribers, auto_renew=auto, ever_paid=ever, revenue_rub=total / 100,
                        months=[MonthPoint(month=m.date(), revenue_rub=s / 100, payments=n) for m, s, n in rows])


@router.post("/subscriptions/{user_id}/grant", response_model=dict[str, datetime])
async def grant(user_id: UUID, body: GrantIn, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> dict[str, datetime]:
    """Продлить или подключить «Базовый» без оплаты — компенсация, сбой оплаты, акция. Всё в аудите с причиной."""
    now = datetime.now(UTC)
    sub = await session.get(Subscription, user_id, with_for_update=True)
    if sub is None:
        sub = Subscription(user_id=user_id, plan=subscriptions.BASIC, period_start=now, period_end=now, auto_renew=False)
        session.add(sub)
    if sub.period_end <= now:
        sub.period_start = now
    sub.period_end = max(now, sub.period_end) + timedelta(days=body.days)
    sub.expired_at = sub.reminded_at = None
    await session.flush()
    await outbox.event(session, "billing.subscription.granted", {"user_id": str(user_id), "days": body.days, "reason": body.reason.strip()},
                       actor_id=principal.user_id)
    await subscriptions.changed(session, sub, "granted")
    await session.commit()
    return {"period_end": sub.period_end}
