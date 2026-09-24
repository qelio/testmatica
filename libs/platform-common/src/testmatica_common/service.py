"""Жизненный цикл сервиса: подключение к брокеру, outbox relay, consumers, health-эндпоинты."""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Sequence

from fastapi import APIRouter

from .config import CommonSettings
from .db import Database
from .errors import ApiError
from .messaging import Broker, Consumer, OutboxRelay
from .messaging.consumer import Handler

log = logging.getLogger(__name__)


class ServiceRuntime:
    def __init__(self, settings: CommonSettings, db: Database) -> None:
        self.settings = settings
        self.db = db
        self.broker = Broker(settings.rabbitmq_url)
        self.consumers: list[Consumer] = []
        self.periodic: list[tuple[str, Callable[[], Awaitable[None]], float]] = []
        self._tasks: list[asyncio.Task] = []

    def consumer(self, queue: str, bindings: Sequence[tuple[str, str]], handler: Handler, **kw) -> Consumer:
        consumer = Consumer(self.broker, self.db, queue, bindings, handler, **kw)
        self.consumers.append(consumer)
        return consumer

    def every(self, name: str, seconds: float, job: Callable[[], Awaitable[None]]) -> None:
        """Периодическая фоновая задача (например, таймеры в БД). Ошибки логируются, цикл продолжается."""
        self.periodic.append((name, job, seconds))

    async def _loop(self, name: str, job: Callable[[], Awaitable[None]], seconds: float) -> None:
        while True:
            try:
                await job()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("periodic job failed", extra={"job": name})
            await asyncio.sleep(seconds)

    async def start(self) -> None:
        if not self.settings.run_background:
            return
        await self._connect_with_retry()
        self._tasks.append(asyncio.create_task(OutboxRelay(self.db, self.broker).run()))
        for consumer in self.consumers:
            await consumer.start()
        for name, job, seconds in self.periodic:
            self._tasks.append(asyncio.create_task(self._loop(name, job, seconds)))

    async def _connect_with_retry(self, attempts: int = 30) -> None:
        for attempt in range(1, attempts + 1):
            try:
                await self.broker.connect()
                return
            except Exception:
                if attempt == attempts:
                    raise
                log.warning("rabbitmq not ready, retrying", extra={"attempt": attempt})
                await asyncio.sleep(2)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self.broker.close()
        await self.db.dispose()


def health_router(db: Database) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @router.get("/ready")
    async def ready() -> dict:
        try:
            await db.ping()
        except Exception:
            raise ApiError(503, "not_ready", "База данных недоступна") from None
        return {"status": "ready"}

    return router
