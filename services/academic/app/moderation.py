"""Решения модератора по шаблонам КТП (moderation.decision.made, kind = plan_template)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .deps import outbox
from .models import TEMPLATE_PENDING, TEMPLATE_PUBLISHED, TEMPLATE_REJECTED, PlanTemplate


async def on_moderation_decision(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    if d.get("kind") != "plan_template":
        return
    t = await session.get(PlanTemplate, UUID(d["ref_id"]), with_for_update=True)
    if t is None or t.status != TEMPLATE_PENDING:
        return  # автор успел отозвать или удалить
    approved = d["decision"] == "approve"
    t.status = TEMPLATE_PUBLISHED if approved else TEMPLATE_REJECTED
    t.review_comment = None if approved else d.get("comment")
    if approved:
        t.published_at = datetime.now(UTC)
    moderator = UUID(d["moderator_id"]) if d.get("moderator_id") else None
    await outbox.event(
        session,
        "academic.plan_template.published" if approved else "academic.plan_template.rejected",
        {"template_id": str(t.id), "title": t.title, "author_id": str(t.owner_id), "comment": t.review_comment},
        actor_id=moderator,
    )
