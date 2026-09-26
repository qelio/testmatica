"""Заявки появляются из событий других сервисов."""

from uuid import UUID

from sqlalchemy import text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .models import PENDING, WITHDRAWN, Person, QueueItem


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


async def on_marketplace_event(envelope: Envelope, session: AsyncSession) -> None:
    """Документы об образовании репетиторов."""
    d = envelope.data
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
