"""Тариф педагога из billing (free / basic) — для проверки лимитов бесплатного тарифа в других сервисах."""

import time
from uuid import UUID

from .errors import ApiError
from .internal import InternalClient

FREE, BASIC = "free", "basic"

# Настройки платформы (меняет администратор в billing). Значения по умолчанию — они же запасные, если billing недоступен.
PLATFORM_DEFAULTS: dict[str, int] = {
    "basic_price_rub": 490,          # цена тарифа «Базовый» в месяц
    "free_max_groups": 3,            # бесплатный тариф: активных классов и групп
    "free_video_minutes": 40,        # бесплатный тариф: длительность бесплатного видеозанятия
    "free_recordings_keep": 3,       # бесплатный тариф: сколько записей занятий хранится
    "free_recording_days": 14,       # бесплатный тариф: сколько дней хранится запись
    "basic_recording_days": 30,      # «Базовый»: сколько дней хранится запись
    "commission_percent": 10,        # комиссия с платных занятий (с оплатой занятий)
    "dispute_window_minutes": 60,    # окно спора после занятия (escrow)
    "payment_deadline_hours": 2,     # оплата не позже чем за N часов до занятия
    "payout_min_rub": 5000,          # автовывод — от этой суммы
}


class Plans:
    """Кэшируется только «Базовый» (коротко): после оплаты новый тариф действует сразу, а окончание — через несколько секунд."""

    def __init__(self, client: InternalClient, ttl_seconds: float = 10) -> None:
        self.client = client
        self.ttl = ttl_seconds
        self._cache: dict[UUID, tuple[float, str]] = {}
        self._settings: tuple[float, dict[str, int]] = (0.0, {})

    def reset(self) -> None:
        self._cache.clear()
        self._settings = (0.0, {})

    async def settings(self) -> dict[str, int]:
        """Настройки платформы из billing (кэш 30 секунд); если billing недоступен — значения по умолчанию."""
        fetched, data = self._settings
        if data and time.monotonic() - fetched < 30:
            return data
        try:
            data = PLATFORM_DEFAULTS | await self.client.get("/internal/settings")
        except ApiError:
            return data or dict(PLATFORM_DEFAULTS)
        self._settings = (time.monotonic(), data)
        return data

    async def many(self, user_ids, fallback: str | None = None) -> dict[UUID, str]:
        """Тарифы нескольких педагогов. fallback — что считать, если billing недоступен (None — пробросить ошибку)."""
        now = time.monotonic()
        ids = set(user_ids)
        result = {u: plan for u, (at, plan) in self._cache.items() if u in ids and now - at < self.ttl}
        missing = [u for u in ids if u not in result]
        if missing:
            try:
                fetched = await self.client.post("/internal/plans", json={"user_ids": [str(u) for u in missing]})
            except ApiError:
                if fallback is None:
                    raise
                fetched = {str(u): fallback for u in missing}
            for u in missing:
                plan = fetched.get(str(u), FREE)
                result[u] = plan
                if plan == BASIC:
                    self._cache[u] = (now, plan)
        return result

    async def of(self, user_id: UUID, fallback: str | None = None) -> str:
        return (await self.many([user_id], fallback))[user_id]
