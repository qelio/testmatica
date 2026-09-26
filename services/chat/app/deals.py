"""Чаты переговоров по заявкам (события marketplace). Писать в них можно без привязки (решение №12)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from . import realtime
from .models import KIND_DEAL, Conversation, ConversationMember, Message

CLOSED = {
    "agreed_other": "Ученик договорился с другим репетитором — переговоры завершены.",
    "student_closed": "Ученик закрыл заявку.",
    "declined_by_tutor": "Репетитор отказался от заявки.",
    "declined_by_student": "Ученик отказался от этого предложения.",
    "expired": "Заявка закрылась: прошло 14 дней.",
}


def _rub(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " ₽"


async def _post(session: AsyncSession, conv_id: UUID, author: UUID, text: str, system: bool, members: list[UUID]) -> None:
    now = datetime.now(UTC)
    msg = Message(conversation_id=conv_id, author_id=author, text=text, attachments=[], is_system=system, created_at=now)
    session.add(msg)
    conv = await session.get(Conversation, conv_id)
    if conv is not None:
        conv.last_message_at = now
    await session.flush()
    # Живое обновление открытого чата; если сообщение не дошло — появится при следующей загрузке.
    await realtime.publish(members, {"type": "refresh", "conversation_id": str(conv_id)})


async def on_marketplace_event(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    conv_id = UUID(d["response_id"])
    student, tutor = UUID(d["student_id"]), UUID(d["tutor_id"])
    members = [student, tutor]
    terms = f"{_rub(d['price'])} за {d['duration_min']} мин"
    t = envelope.type
    if t == "marketplace.response.created":
        await session.execute(
            insert(Conversation).values(id=conv_id, kind=KIND_DEAL, title=f"заявка: {d['subject']}").on_conflict_do_nothing()
        )
        for uid in members:
            await session.execute(
                insert(ConversationMember).values(conversation_id=conv_id, user_id=uid, role="member").on_conflict_do_nothing()
            )
        intro = ("Ученик хочет заниматься с вами" if d.get("direct") else "Репетитор откликнулся на заявку") + f": {d['subject']}. Цена — {terms}."
        await _post(session, conv_id, student if d.get("direct") else tutor, intro, True, members)
        if d.get("message"):
            await _post(session, conv_id, student if d.get("direct") else tutor, d["message"], False, members)
    elif t == "marketplace.response.price_proposed":
        who = "Ученик" if d["by"] == "student" else "Репетитор"
        await _post(session, conv_id, student if d["by"] == "student" else tutor, f"{who} предлагает цену: {terms}.", True, members)
    elif t == "marketplace.deal.agreed":
        await _post(session, conv_id, envelope.actor_id or student,
                    f"✅ Договорились: {terms}. Ученик привязан к репетитору — занятия можно ставить в расписание.", True, members)
    elif t == "marketplace.response.closed":
        text = CLOSED.get(d.get("reason", ""), "Переговоры завершены.")
        await _post(session, conv_id, envelope.actor_id or student, text, True, members)
