"""Получатель сообщений из RabbitMQ.

Для очереди Q объявляются:
  Q        — основная очередь;
  Q.retry  — сообщения с ошибкой ждут здесь retry_delay_ms и возвращаются в Q;
  Q.dlq    — после max_attempts неудачных попыток сообщение уходит сюда для ручного разбора.

Обработчик выполняется в транзакции вместе с записью в inbox, поэтому одно и то же
сообщение (повторная доставка) обрабатывается ровно один раз.
"""

import logging
from collections.abc import Awaitable, Callable, Sequence

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import Database
from .broker import Broker, declare_exchanges
from .envelope import Envelope

log = logging.getLogger(__name__)

Handler = Callable[[Envelope, AsyncSession], Awaitable[None]]


class Consumer:
    def __init__(
        self,
        broker: Broker,
        db: Database,
        queue: str,
        bindings: Sequence[tuple[str, str]],
        handler: Handler,
        max_attempts: int = 5,
        retry_delay_ms: int = 5000,
        prefetch: int = 10,
    ) -> None:
        self.broker = broker
        self.db = db
        self.queue = queue
        self.bindings = bindings
        self.handler = handler
        self.max_attempts = max_attempts
        self.retry_delay_ms = retry_delay_ms
        self.prefetch = prefetch
        self._channel: AbstractChannel | None = None

    async def start(self) -> None:
        assert self.broker.connection is not None, "Broker.connect() не вызван"
        channel = await self.broker.connection.channel()
        await channel.set_qos(prefetch_count=self.prefetch)
        exchanges = await declare_exchanges(channel)

        queue = await channel.declare_queue(self.queue, durable=True)
        await channel.declare_queue(
            f"{self.queue}.retry",
            durable=True,
            arguments={
                "x-message-ttl": self.retry_delay_ms,
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": self.queue,
            },
        )
        await channel.declare_queue(f"{self.queue}.dlq", durable=True)
        for exchange, routing_key in self.bindings:
            await queue.bind(exchanges[exchange], routing_key=routing_key)

        self._channel = channel
        await queue.consume(self._on_message)
        log.info("consumer started", extra={"queue": self.queue})

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        try:
            envelope = Envelope.model_validate_json(message.body)
        except ValidationError:
            log.error("malformed message", extra={"queue": self.queue})
            await self._forward(message, f"{self.queue}.dlq", attempt=0)
            await message.ack()
            return

        try:
            await self.process(envelope)
        except Exception:
            attempt = int((message.headers or {}).get("x-attempt", 0)) + 1
            final = attempt >= self.max_attempts
            log.exception(
                "handler failed",
                extra={
                    "queue": self.queue,
                    "event_id": str(envelope.event_id),
                    "type": envelope.type,
                    "attempt": attempt,
                    "to_dlq": final,
                },
            )
            target = f"{self.queue}.dlq" if final else f"{self.queue}.retry"
            await self._forward(message, target, attempt)
        await message.ack()

    async def process(self, envelope: Envelope) -> bool:
        """Обработать сообщение с защитой от дублей. Возвращает False, если оно уже обработано."""
        async with self.db.sessionmaker() as session, session.begin():
            inserted = await session.execute(
                text(
                    "INSERT INTO inbox (event_id, consumer) VALUES (:id, :consumer) "
                    "ON CONFLICT DO NOTHING RETURNING event_id"
                ),
                {"id": envelope.event_id, "consumer": self.queue},
            )
            if inserted.first() is None:
                return False
            await self.handler(envelope, session)
            return True

    async def _forward(self, message: AbstractIncomingMessage, queue: str, attempt: int) -> None:
        assert self._channel is not None
        await self._channel.default_exchange.publish(
            aio_pika.Message(
                message.body,
                message_id=message.message_id,
                content_type=message.content_type,
                headers={"x-attempt": attempt},
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=queue,
        )
