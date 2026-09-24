from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .models import AuditRecord


async def on_event(envelope: Envelope, session: AsyncSession) -> None:
    await session.execute(
        insert(AuditRecord)
        .values(
            event_id=envelope.event_id,
            type=envelope.type,
            version=envelope.version,
            producer=envelope.producer,
            actor_id=envelope.actor_id,
            occurred_at=envelope.occurred_at,
            data=envelope.data,
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
    )
