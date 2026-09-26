"""Заявки появляются из событий других сервисов."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .models import PENDING, WITHDRAWN, Person, QueueItem, Subscriber


async def on_identity_event(envelope: Envelope, session: AsyncSession) -> None:
    if envelope.type in ("identity.user.registered", "identity.user.snapshot", "identity.user.updated"):
        d = envelope.data
        await session.execute(
            insert(Person)
            .values(user_id=UUID(d["user_id"]), full_name=d["full_name"])
            .on_conflict_do_update(index_elements=["user_id"], set_={"full_name": d["full_name"]})
        )


async def on_content_event(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    if envelope.type == "content.course.submitted":
        await session.execute(
            insert(QueueItem)
            .values(
                kind="course",
                ref_id=UUID(d["course_id"]),
                title=d["title"],
                author_id=UUID(d["author_id"]),
                details={"materials_count": d.get("materials_count")},
                status=PENDING,
            )
            .on_conflict_do_nothing(index_elements=["kind", "ref_id"], index_where=text("status = 'pending'"))
        )
    elif envelope.type in ("content.course.unpublished", "content.course.deleted"):
        # Автор отозвал курс с проверки — заявка закрывается.
        await session.execute(
            update(QueueItem)
            .where(QueueItem.kind == "course", QueueItem.ref_id == UUID(d["course_id"]), QueueItem.status == PENDING)
            .values(status=WITHDRAWN)
        )


async def on_academic_event(envelope: Envelope, session: AsyncSession) -> None:
    """Шаблоны КТП в публичную библиотеку."""
    d = envelope.data
    if envelope.type == "academic.plan_template.submitted":
        await session.execute(
            insert(QueueItem)
            .values(kind="plan_template", ref_id=UUID(d["template_id"]), title=d["title"], author_id=UUID(d["author_id"]),
                    details={"lessons_count": d.get("lessons_count"), "subject": d.get("subject")}, status=PENDING)
            .on_conflict_do_nothing(index_elements=["kind", "ref_id"], index_where=text("status = 'pending'"))
        )
    elif envelope.type == "academic.plan_template.unpublished":
        await session.execute(
            update(QueueItem)
            .where(QueueItem.kind == "plan_template", QueueItem.ref_id == UUID(d["template_id"]), QueueItem.status == PENDING)
            .values(status=WITHDRAWN)
        )


async def _submit(session: AsyncSession, kind: str, ref_id: UUID, title: str, author_id: UUID, details: dict) -> None:
    """Новая заявка; если по объекту уже есть открытая — обновить её (автор отредактировал до проверки)."""
    values = {"title": title[:300], "author_id": author_id, "details": details}
    await session.execute(
        insert(QueueItem)
        .values(kind=kind, ref_id=ref_id, status=PENDING, **values)
        .on_conflict_do_update(index_elements=["kind", "ref_id"], index_where=text("status = 'pending'"), set_=values)
    )


async def _withdraw(session: AsyncSession, kinds: tuple[str, ...], ref_id: UUID) -> None:
    await session.execute(
        update(QueueItem)
        .where(QueueItem.kind.in_(kinds), QueueItem.ref_id == ref_id, QueueItem.status == PENDING)
        .values(status=WITHDRAWN)
    )


async def _on_review_event(t: str, d: dict, session: AsyncSession) -> None:
    """Отзывы: сам отзыв (автор — ученик), ответ педагога и спор (автор — педагог)."""
    ref = UUID(d["review_id"])
    rating = f"{d['rating']}/10" if d.get("rating") else ""
    common = {"rating": d.get("rating"), "tutor_id": d.get("tutor_id"), "tutor_name": d.get("tutor_name"),
              "student_name": d.get("student_name")}
    if t == "marketplace.review.submitted":
        # Отзыв изменён — прежние ответ и спор относились к старой версии.
        await _withdraw(session, ("review_reply", "review_dispute"), ref)
        await _submit(session, "review", ref, f"Отзыв о педагоге {d['tutor_name']}: {rating}", UUID(d["student_id"]),
                      common | {"text": d["text"]})
    elif t == "marketplace.review.reply_submitted":
        await _submit(session, "review_reply", ref, f"Ответ на отзыв {d['student_name']} ({rating})", UUID(d["tutor_id"]),
                      common | {"text": d["text"], "review_text": d.get("review_text")})
    elif t == "marketplace.review.reply_withdrawn":
        await _withdraw(session, ("review_reply",), ref)
    elif t == "marketplace.review.disputed":
        await _submit(session, "review_dispute", ref, f"Спор по отзыву {d['student_name']} ({rating})", UUID(d["tutor_id"]),
                      common | {"reason": d["reason"], "review_text": d.get("text"), "dispute_id": d["dispute_id"]})
    elif t in ("marketplace.review.withdrawn", "marketplace.review.removed"):
        kinds = ("review", "review_reply", "review_dispute") if t.endswith("withdrawn") else ("review_reply", "review_dispute")
        await _withdraw(session, kinds, ref)


async def on_marketplace_event(envelope: Envelope, session: AsyncSession) -> None:
    """Документы об образовании и отзывы о репетиторах."""
    d = envelope.data
    if envelope.type.startswith("marketplace.review."):
        await _on_review_event(envelope.type, d, session)
        return
    if envelope.type == "marketplace.education.submitted":
        await session.execute(
            insert(QueueItem)
            .values(kind="education_doc", ref_id=UUID(d["doc_id"]), title=d["title"], author_id=UUID(d["user_id"]),
                    details={"institution": d.get("institution"), "year": d.get("year")}, status=PENDING)
            .on_conflict_do_nothing(index_elements=["kind", "ref_id"], index_where=text("status = 'pending'"))
        )
    elif envelope.type == "marketplace.education.withdrawn":
        await session.execute(
            update(QueueItem)
            .where(QueueItem.kind == "education_doc", QueueItem.ref_id == UUID(d["doc_id"]), QueueItem.status == PENDING)
            .values(status=WITHDRAWN)
        )


async def on_assessment_event(envelope: Envelope, session: AsyncSession) -> None:
    d = envelope.data
    if envelope.type == "assessment.task.submitted":
        await session.execute(
            insert(QueueItem)
            .values(kind="task", ref_id=UUID(d["task_id"]), title=d["title"], author_id=UUID(d["author_id"]),
                    details={"type": d.get("type")}, status=PENDING)
            .on_conflict_do_nothing(index_elements=["kind", "ref_id"], index_where=text("status = 'pending'"))
        )
    elif envelope.type in ("assessment.task.unpublished", "assessment.task.deleted"):
        await session.execute(
            update(QueueItem)
            .where(QueueItem.kind == "task", QueueItem.ref_id == UUID(d["task_id"]), QueueItem.status == PENDING)
            .values(status=WITHDRAWN)
        )


async def on_billing_event(envelope: Envelope, session: AsyncSession) -> None:
    """Подписка изменилась: «Базовый» — приоритет в очереди до конца периода."""
    d = envelope.data
    if envelope.type != "billing.subscription.changed":
        return
    user_id = UUID(d["user_id"])
    if d["plan"] == "basic":
        until = datetime.fromisoformat(d["period_end"])
        await session.execute(
            insert(Subscriber).values(user_id=user_id, until=until).on_conflict_do_update(index_elements=["user_id"], set_={"until": until})
        )
    else:
        await session.execute(delete(Subscriber).where(Subscriber.user_id == user_id))
