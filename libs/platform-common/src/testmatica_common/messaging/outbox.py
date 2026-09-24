"""Transactional outbox.

Сервис пишет событие в таблицу outbox в той же транзакции, что и изменение данных.
OutboxRelay отдельно забирает неотправленные строки и публикует их в RabbitMQ.
Гарантия — «как минимум один раз»: дубликаты отсекает inbox на стороне получателя.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import Database
from ..ids import uuid7
from .broker import Broker
from .envelope import COMMANDS_EXCHANGE, EVENTS_EXCHANGE, Envelope

log = logging.getLogger(__name__)

_INSERT = text(
    "INSERT INTO outbox (id, exchange, routing_key, payload) "
    "VALUES (:id, :exchange, :routing_key, CAST(:payload AS jsonb))"
)


class Outbox:
    def __init__(self, producer: str) -> None:
        self.producer = producer

    async def event(
        self,
        session: AsyncSession,
        type: str,
        data: dict[str, Any],
        actor_id: UUID | None = None,
        version: int = 1,
    ) -> UUID:
        return await self._add(session, EVENTS_EXCHANGE, type, type, data, actor_id, version)

    async def command(
        self,
        session: AsyncSession,
        queue: str,
        type: str,
        data: dict[str, Any],
        actor_id: UUID | None = None,
    ) -> UUID:
        return await self._add(session, COMMANDS_EXCHANGE, queue, type, data, actor_id, 1)

    async def _add(self, session, exchange, routing_key, type, data, actor_id, version) -> UUID:
        envelope = Envelope(
            event_id=uuid7(),
            type=type,
            version=version,
            occurred_at=datetime.now(UTC),
            producer=self.producer,
            actor_id=actor_id,
            data=data,
        )
        await session.execute(
            _INSERT,
            {
                "id": envelope.event_id,
                "exchange": exchange,
                "routing_key": routing_key,
                "payload": envelope.model_dump_json(),
            },
        )
        return envelope.event_id


class OutboxRelay:
    def __init__(self, db: Database, broker: Broker, batch_size: int = 100, interval: float = 0.5):
        self.db = db
        self.broker = broker
        self.batch_size = batch_size
        self.interval = interval

    async def run(self) -> None:
        while True:
            try:
                sent = await self.publish_batch()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("outbox relay failed")
                await asyncio.sleep(2)
                continue
            if sent < self.batch_size:
                await asyncio.sleep(self.interval)

    async def publish_batch(self) -> int:
        async with self.db.sessionmaker() as session, session.begin():
            # SKIP LOCKED: несколько экземпляров сервиса не отправят одну строку одновременно.
            rows = (
                await session.execute(
                    text(
                        "SELECT id, exchange, routing_key, payload::text AS payload FROM outbox "
                        "WHERE published_at IS NULL ORDER BY created_at "
                        "LIMIT :n FOR UPDATE SKIP LOCKED"
                    ),
                    {"n": self.batch_size},
                )
            ).all()
            for row in rows:
                await self.broker.publish(
                    row.exchange, row.routing_key, row.payload.encode(), str(row.id)
                )
            if rows:
                await session.execute(
                    text("UPDATE outbox SET published_at = now() WHERE id = ANY(:ids)"),
                    {"ids": [row.id for row in rows]},
                )
            return len(rows)
