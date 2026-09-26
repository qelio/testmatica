"""Справочник предметов из content (ведут модераторы): проверка, что предмет выбран из списка."""

import time

from .errors import ApiError
from .internal import InternalClient


class Subjects:
    def __init__(self, client: InternalClient, ttl_seconds: float = 300) -> None:
        self.client = client
        self.ttl = ttl_seconds
        self._names: set[str] = set()
        self._fetched = 0.0

    def reset(self) -> None:
        self._names, self._fetched = set(), 0.0

    async def names(self, refresh: bool = False) -> set[str]:
        if refresh or not self._names or time.monotonic() - self._fetched > self.ttl:
            self._names = {s["name"] for s in await self.client.get("/subjects")}
            self._fetched = time.monotonic()
        return self._names

    async def check(self, name: str | None) -> None:
        """Пустой предмет — можно; иначе только из справочника (новый предмет подхватится без ожидания кэша)."""
        if not name:
            return
        if name in await self.names() or name in await self.names(refresh=True):
            return
        raise ApiError(422, "unknown_subject", "Выберите предмет из списка")
