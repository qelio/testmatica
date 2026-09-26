"""Тариф педагога из billing (free / basic) — для проверки лимитов бесплатного тарифа в других сервисах."""

import time
from uuid import UUID

from .errors import ApiError
from .internal import InternalClient

FREE, BASIC = "free", "basic"


class Plans:
    """Кэшируется только «Базовый» (коротко): после оплаты новый тариф действует сразу, а окончание — через несколько секунд."""

    def __init__(self, client: InternalClient, ttl_seconds: float = 10) -> None:
        self.client = client
        self.ttl = ttl_seconds
        self._cache: dict[UUID, tuple[float, str]] = {}

    def reset(self) -> None:
        self._cache.clear()

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
