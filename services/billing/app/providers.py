"""Платёжные провайдеры. Сейчас — только поддельный: оплата подтверждается на тестовой странице сайта.
Настоящий (ЮKassa) реализует тот же интерфейс: создать платёж со страницей оплаты и списать сохранённым способом."""

from dataclasses import dataclass
from typing import Protocol

from testmatica_common.errors import ApiError

from .config import settings
from .models import Payment


@dataclass
class Created:
    provider_payment_id: str
    confirmation_url: str


@dataclass
class Charged:
    provider_payment_id: str
    succeeded: bool
    error: str | None = None


class PaymentProvider(Protocol):
    name: str

    async def create(self, payment: Payment) -> Created:
        """Платёж с переходом на страницу оплаты провайдера."""

    async def charge(self, payment: Payment, method_id: str) -> Charged:
        """Списание сохранённым способом оплаты (автопродление) — без участия пользователя."""


class FakeProvider:
    """Поддельный провайдер для разработки: деньги не списываются.
    Страница оплаты — /dashboard/pay/<id> на нашем сайте; результат она сообщает в POST /fake-provider/payments/<id>."""

    name = "fake"
    DECLINED_SUFFIX = "0002"  # карта «…0002» — отказ банка, как у тестовых карт настоящих провайдеров

    async def create(self, payment: Payment) -> Created:
        return Created(provider_payment_id=f"fake_{payment.id}", confirmation_url=f"{settings.web_base_url}/dashboard/pay/{payment.id}")

    async def charge(self, payment: Payment, method_id: str) -> Charged:
        declined = method_id.endswith(self.DECLINED_SUFFIX)
        return Charged(provider_payment_id=f"fake_{payment.id}", succeeded=not declined,
                       error="Банк отклонил списание" if declined else None)


def get_provider() -> PaymentProvider:
    if settings.payment_provider == "fake":
        return FakeProvider()
    if settings.payment_provider == "disabled":
        # Прод до подключения ЮKassa: поддельная оплата там недопустима, тариф выдаёт администратор.
        raise ApiError(503, "payments_unavailable", "Оплата тарифа скоро появится. Пока подключить «Базовый» можно через поддержку.")
    raise RuntimeError(f"Неизвестный платёжный провайдер: {settings.payment_provider}")
