"""«Договорились» в маркетплейсе: ученик привязывается к репетитору, индивидуальные занятия — платные по этой цене."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from . import logic
from .deps import outbox
from .models import SOURCE_MARKETPLACE


async def on_marketplace_event(envelope: Envelope, session: AsyncSession) -> None:
    if envelope.type != "marketplace.deal.agreed":
        return
    d = envelope.data
    teacher, student = UUID(d["tutor_id"]), UUID(d["student_id"])
    link = await logic.activate_link(session, teacher, student, SOURCE_MARKETPLACE, envelope.actor_id or student)
    link.paid, link.price, link.lesson_minutes = True, d["price"], d["duration_min"]
    await outbox.event(
        session, "classroom.link.billing_changed",
        {"teacher_id": str(teacher), "student_id": str(student), "paid": True, "price": d["price"], "lesson_minutes": d["duration_min"]},
        actor_id=envelope.actor_id,
    )
