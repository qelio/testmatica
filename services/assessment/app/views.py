from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal

from . import access
from .models import CHOICE, Exam, ExamItem, Person, Submission, Task, Topic
from .schemas import ExamLabel, FileRef, OptionOut, SubmissionOut, TaskOut, TaskSummary


async def names(session: AsyncSession, ids) -> dict[UUID, str]:
    ids = set(ids)
    if not ids:
        return {}
    return dict((await session.execute(select(Person.user_id, Person.full_name).where(Person.user_id.in_(ids)))).all())


async def topic_paths(session: AsyncSession, ids) -> dict[UUID, list[str]]:
    """Путь в рубрикаторе: [раздел, тема] (или только раздел)."""
    ids = {i for i in ids if i}
    if not ids:
        return {}
    topics = {t.id: t for t in (await session.execute(select(Topic).where(Topic.id.in_(ids)))).scalars()}
    parents = {t.id: t for t in (await session.execute(
        select(Topic).where(Topic.id.in_({t.parent_id for t in topics.values() if t.parent_id}))
    )).scalars()}
    return {i: ([parents[t.parent_id].title] if t.parent_id in parents else []) + [t.title] for i, t in topics.items()}


EXAM_KINDS = {"ege": "ЕГЭ", "oge": "ОГЭ"}


async def exam_labels(session: AsyncSession, ids) -> dict[UUID, ExamLabel]:
    """Подписи заданий экзамена: «ЕГЭ №8» + название."""
    ids = set(ids)
    if not ids:
        return {}
    rows = await session.execute(
        select(ExamItem.id, ExamItem.number, ExamItem.title, Exam.kind).join(Exam, Exam.id == ExamItem.exam_id).where(ExamItem.id.in_(ids))
    )
    return {i: ExamLabel(id=i, label=f"{EXAM_KINDS[kind]} №{n}", title=title) for i, n, title, kind in rows}


def summary(t: Task, authors: dict[UUID, str], paths: dict[UUID, list[str]], labels: dict[UUID, ExamLabel] | None = None) -> TaskSummary:
    return TaskSummary(
        id=t.id, title=t.title, type=t.type, difficulty=t.difficulty, subject_id=t.subject_id, subject_name=t.subject_name,
        topic_id=t.topic_id, topic_path=paths.get(t.topic_id, []), tags=t.tags,
        exam_items=[labels[i] for i in t.exam_item_ids if labels and i in labels], status=t.status, owner_id=t.owner_id, author_name=authors.get(t.owner_id, "Автор"), updated_at=t.updated_at,
    )


async def summaries(session: AsyncSession, tasks: Sequence[Task]) -> list[TaskSummary]:
    authors = await names(session, {t.owner_id for t in tasks})
    paths = await topic_paths(session, {t.topic_id for t in tasks})
    labels = await exam_labels(session, {i for t in tasks for i in t.exam_item_ids})
    return [summary(t, authors, paths, labels) for t in tasks]


async def full(session: AsyncSession, t: Task, p: Principal | None) -> TaskOut:
    await session.refresh(t)
    key = access.can_see_key(t, p)
    authors = await names(session, [t.owner_id])
    return TaskOut(
        **summary(t, authors, await topic_paths(session, [t.topic_id]), await exam_labels(session, t.exam_item_ids)).model_dump(),
        statement=t.statement,
        explanation=t.explanation if key else "",
        theory_material_id=t.theory_material_id,
        file_mode=t.file_mode,
        options=[OptionOut(id=o.id, text=o.text, is_correct=o.is_correct if key else None) for o in t.options],
        answers=t.answers if key else None,
        starter_code=t.starter_code,
        time_limit_s=t.time_limit_s,
        memory_limit_mb=t.memory_limit_mb,
        tests=[{"input": c.input, "expected": c.expected} for c in t.tests] if key else None,
        review_comment=t.review_comment if p is not None and (t.owner_id == p.user_id or access.is_staff(p)) else None,
        can_edit=p is not None and access.can_edit(t, p),
        multiple=t.type == CHOICE and sum(o.is_correct for o in t.options) > 1,
    )


def submission_out(s: Submission, with_log: bool, urls: dict[str, str] | None = None) -> SubmissionOut:
    urls = urls or {}
    return SubmissionOut(
        id=s.id, task_id=s.task_id, student_id=s.student_id, context_type=s.context_type, context_id=s.context_id,
        answer=s.answer, files=[FileRef(**f, url=urls.get(f["id"])) for f in s.files], status=s.status, score=s.score,
        failed_case=s.failed_case, failure=s.failure, teacher_comment=s.teacher_comment, created_at=s.created_at,
        checked_at=s.checked_at, run_log=s.run_log if with_log else None,
    )
