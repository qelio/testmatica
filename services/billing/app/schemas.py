from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class PaymentOut(BaseModel):
    id: UUID
    purpose: str
    description: str
    amount_rub: float
    status: str
    recurring: bool
    confirmation_url: str | None
    error: str | None
    created_at: datetime
    paid_at: datetime | None


class SubscriptionOut(BaseModel):
    plan: Literal["free", "basic"]
    period_end: datetime | None = Field(description="До какого момента действует «Базовый» (или когда закончился)")
    auto_renew: bool
    payment_method_title: str | None
    price_rub: int = Field(description="Цена тарифа «Базовый» за месяц")
    pending_payment: PaymentOut | None


class CheckoutIn(BaseModel):
    auto_renew: bool = Field(True, description="Сохранить способ оплаты и продлевать автоматически")
    accept_offer: bool = Field(description="Принимаю условия публичной оферты (акцепт — оплата с этой галочкой)")

    @field_validator("accept_offer")
    @classmethod
    def _offer(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Чтобы оплатить, примите условия оферты")
        return value


class AutoRenewIn(BaseModel):
    enabled: bool


class FakeResultIn(BaseModel):
    outcome: Literal["success", "cancel"]
    card_last4: str = Field("4242", pattern=r"^\d{4}$", description="Карта …0002 — отказ банка")


class PlansIn(BaseModel):
    user_ids: list[UUID] = Field(max_length=500)
