import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractRobustConnection

from .envelope import COMMANDS_EXCHANGE, EVENTS_EXCHANGE


class Broker:
    """Подключение к RabbitMQ. connect_robust сам переподключается при обрыве."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchanges: dict[str, AbstractExchange] = {}

    async def connect(self) -> None:
        self.connection = await aio_pika.connect_robust(self.url)
        # publisher_confirms: publish() ждёт подтверждения от брокера, что сообщение принято.
        self._channel = await self.connection.channel(publisher_confirms=True)
        self._exchanges = await declare_exchanges(self._channel)

    async def publish(self, exchange: str, routing_key: str, body: bytes, message_id: str) -> None:
        assert self._channel is not None, "Broker.connect() не вызван"
        target = self._exchanges[exchange] if exchange else self._channel.default_exchange
        await target.publish(
            aio_pika.Message(
                body,
                message_id=message_id,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=routing_key,
        )

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()


async def declare_exchanges(channel: AbstractChannel) -> dict[str, AbstractExchange]:
    return {
        EVENTS_EXCHANGE: await channel.declare_exchange(
            EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        ),
        COMMANDS_EXCHANGE: await channel.declare_exchange(
            COMMANDS_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True
        ),
    }
