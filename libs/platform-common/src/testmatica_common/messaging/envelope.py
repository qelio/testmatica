from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# Доменные события: «что-то произошло». Topic-exchange, ключ = тип события
# (например, identity.user.registered). Подписаться может кто угодно, включая audit.
EVENTS_EXCHANGE = "events"

# Команды: «сделай это» для конкретного сервиса. Direct-exchange, ключ = имя очереди
# (например, notification.email). Audit их не видит — в командах бывают коды подтверждения.
COMMANDS_EXCHANGE = "commands"


class Envelope(BaseModel):
    event_id: UUID
    type: str
    version: int = 1
    occurred_at: datetime
    producer: str
    actor_id: UUID | None = None
    data: dict[str, Any] = Field(default_factory=dict)
