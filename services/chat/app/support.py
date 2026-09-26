"""Чат поддержки по спору об отзыве (ТЗ: «Педагог может оспорить отзыв — открывается чат с модератором»)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .deals import _post
from .models import KIND_SUPPORT, Conversation, ConversationMember, Person

STAFF_ROLES = ("moderator", "admin")


async def _staff(session: AsyncSession) -> list[UUID]:
    rows = await session.execute(select(Person.user_id).where(Person.roles.overlap(list(STAFF_ROLES))))
    return list(rows.scalars())


async def on_review_event(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    if envelope.type == "marketplace.review.disputed":
        conv_id, tutor = UUID(d["dispute_id"]), UUID(d["tutor_id"])
        await session.execute(
            insert(Conversation)
            .values(id=conv_id, kind=KIND_SUPPORT, title=f"Спор по отзыву · {d['tutor_name']}")
            .on_conflict_do_nothing()
        )
        # Педагог и все модераторы: ответить может любой из них.
        members = [(tutor, "member")] + [(uid, "staff") for uid in await _staff(session) if uid != tutor]
        for uid, role in members:
            await session.execute(
                insert(ConversationMember).values(conversation_id=conv_id, user_id=uid, role=role).on_conflict_do_nothing()
            )
        text = (
            f"Педагог оспаривает отзыв ученика {d['student_name']} (оценка {d['rating']}/10):\n«{d['text']}»\n\n"
            f"Причина: {d['reason']}\n\nМодератор ответит здесь и примет решение: удалить отзыв или оставить."
        )
        await _post(session, conv_id, tutor, text, True, [uid for uid, _ in members])
    elif envelope.type == "marketplace.review.dispute_resolved":
        conv_id = UUID(d["dispute_id"])
        if await session.get(Conversation, conv_id) is None:
            return
        comment = f" Комментарий: {d['comment']}" if d.get("comment") else ""
        text = ("✅ Модератор удалил отзыв." if d["upheld"] else "Модератор оставил отзыв опубликованным.") + comment
        members = list((await session.execute(
            select(ConversationMember.user_id).where(ConversationMember.conversation_id == conv_id)
        )).scalars())
        await _post(session, conv_id, envelope.actor_id or UUID(d["tutor_id"]), text, True, members)
