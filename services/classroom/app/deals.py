"""События маркетплейса.

«Договорились» — ученик привязывается к репетитору, индивидуальные занятия — платные по этой цене.
Набор в группу запущен — создаётся группа с id набора, все записавшиеся привязываются к педагогу и входят в неё (ТЗ, раздел 4).
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from . import logic
from .deps import outbox
from .models import SOURCE_MARKETPLACE, Group


async def on_marketplace_event(envelope: Envelope, session: AsyncSession) -> None:
    if envelope.type in ("marketplace.group_offer.started", "marketplace.group_offer.joined"):
        await _group_offer(envelope, session)
        return
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


async def _group_offer(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    teacher = UUID(d["tutor_id"])
    group = await session.get(Group, UUID(d["offer_id"]), with_for_update=True)
    if envelope.type == "marketplace.group_offer.started" and group is None:
        # Лимит бесплатного тарифа marketplace проверил перед запуском (/internal/group-limit).
        group = Group(id=UUID(d["offer_id"]), teacher_id=teacher, kind="group", title=d["title"][:120], subject=d.get("subject"),
                      paid=d["price"] > 0, description=d.get("description", "")[:2000])
        session.add(group)
        await session.flush()
        await outbox.event(session, "classroom.group.created", {
            "group_id": str(group.id), "teacher_id": str(teacher), "title": group.title, "paid": group.paid, "offer_id": d["offer_id"]},
            actor_id=teacher)
    if group is None or group.archived_at is not None:
        return
    student_ids = d["student_ids"] if "student_ids" in d else [d["student_id"]]
    for sid in map(UUID, student_ids):
        await logic.activate_link(session, teacher, sid, SOURCE_MARKETPLACE, envelope.actor_id or sid)
        await logic.add_member(session, group, sid, envelope.actor_id or teacher)
