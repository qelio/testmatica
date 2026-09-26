from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "billing"

    web_base_url: str = "http://localhost:8080"

    # Платёжный провайдер: пока только поддельный (fake) — оплата подтверждается на тестовой странице.
    payment_provider: str = "fake"
    # Автопродление пробуем за сутки до конца периода; напоминание без автопродления — за 3 дня.
    renew_before_hours: int = 24
    remind_before_days: int = 3


settings = Settings()
