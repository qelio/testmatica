"""События identity (имена) и moderation (решения по документам об образовании)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .deps import outbox
from .models import APPROVED, PENDING, REJECTED, EducationDoc, Person, TutorProfile


async def on_identity_event(envelope: Envelope, session: AsyncSession) -> None:
    if envelope.type in ("identity.user.registered", "identity.user.snapshot", "identity.user.updated"):
        d = envelope.data
        values = {"user_id": UUID(d["user_id"]), "full_name": d["full_name"]}
        update = {"full_name": d["full_name"]}
        if d.get("roles") is not None:
            values["roles"] = update["roles"] = d["roles"]
        await session.execute(insert(Person).values(**values).on_conflict_do_update(index_elements=["user_id"], set_=update))


async def on_moderation_decision(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    if d.get("kind") != "education_doc":
        return
    doc = await session.get(EducationDoc, UUID(d["ref_id"]), with_for_update=True)
    if doc is None or doc.status != PENDING:
        return
    approved = d["decision"] == "approve"
    doc.status, doc.comment, doc.decided_at = (APPROVED if approved else REJECTED), d.get("comment"), datetime.now(UTC)
    profile = await session.get(TutorProfile, doc.user_id, with_for_update=True)
    if profile is not None and approved:
        profile.education_verified = True
    await outbox.event(
        session, "marketplace.education.approved" if approved else "marketplace.education.rejected",
        {"doc_id": str(doc.id), "user_id": str(doc.user_id), "title": doc.title, "comment": doc.comment},
        actor_id=UUID(d["moderator_id"]) if d.get("moderator_id") else None,
    )
