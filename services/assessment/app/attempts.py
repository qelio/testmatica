"""Попытки прохождения тестов и ДЗ: таймеры, сдача, подсчёт баллов и оценки.

Пока попытка идёт, ответы — черновики (attempt_answers). При сдаче каждый ответ становится отправкой
(submissions, context_type = assignment, context_id = id попытки) и проверяется как обычно:
выбор и короткий ответ — сразу, код — в песочнице, развёрнутый — педагогом. Когда проверено всё,
считается итог, ставится оценка и (если педагог настроил) она уходит в журнал.
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import checker
from .deps import db, outbox
from .models import (
    CHECKING,
    CHOICE,
    CODE,
    CORRECT,
    ERROR,
    IN_PROGRESS,
    INCORRECT,
    PENDING_REVIEW,
    REVIEWED,
    SHORT,
    SUBMITTED,
    Assignment,
    AssignmentStudent,
    Attempt,
    AttemptAnswer,
    Submission,
    Task,
)

log = logging.getLogger(__name__)

# Запас на сетевые задержки: ответ, отправленный на последней секунде, не должен потеряться.
GRACE = timedelta(seconds=5)
# Процент → оценка по пятибалльной шкале.
GRADE_SCALE = ((85, 5), (65, 4), (45, 3))
NOT_FINAL = (CHECKING, PENDING_REVIEW, ERROR)


def grade_for(percent: float) -> int:
    return next((g for bound, g in GRADE_SCALE if percent >= bound), 2)


def per_task_limit(a: Assignment) -> timedelta | None:
    s = a.settings
    return timedelta(seconds=s["time_limit_s"]) if s.get("time_mode") == "per_task" and s.get("time_limit_s") else None


def current_ends_at(attempt: Attempt, a: Assignment) -> datetime | None:
    limit = per_task_limit(a)
    if limit is None or attempt.current_started_at is None:
        return None
    return attempt.current_started_at + limit


def deadline_for(a: Assignment, row: AssignmentStudent | None) -> datetime | None:
    """Личный дедлайн (после переназначения) важнее общего."""
    return (row.deadline if row and row.deadline else None) or a.deadline


def sync_timer(attempt: Attempt, a: Assignment, now: datetime, deadline: datetime | None) -> bool:
    """Продвинуть таймер «на каждое задание» и понять, пора ли сдавать попытку автоматически."""
    if attempt.status != IN_PROGRESS:
        return False
    if a.closed_at is not None:
        return True
    if attempt.ends_at and now >= attempt.ends_at + GRACE:
        return True
    if deadline and now >= deadline + GRACE:
        return True
    limit = per_task_limit(a)
    if limit is not None and attempt.current_started_at is not None:
        while now >= attempt.current_started_at + limit + GRACE:
            attempt.current_index += 1
            attempt.current_started_at += limit
            if attempt.current_index >= len(attempt.task_order):
                return True
    return False


def build_submission(task: Task, answer: dict, files: list[dict], student_id: UUID, attempt_id: UUID, now: datetime) -> Submission | None:
    """Черновик → отправка. Пустой или некорректный ответ — не отправка: за задание 0 баллов."""
    sub = Submission(task_id=task.id, student_id=student_id, context_type="assignment", context_id=attempt_id, created_at=now)
    if task.type == CHOICE:
        valid = {str(o.id) for o in task.options}
        chosen = {str(i) for i in answer.get("option_ids") or []}
        if not chosen or not chosen <= valid:
            return None
        sub.answer = {"option_ids": sorted(chosen)}
        sub.status = CORRECT if checker.check_choice(task, {UUID(i) for i in chosen}) else INCORRECT
    elif task.type == SHORT:
        text = (answer.get("text") or "").strip()
        if not text:
            return None
        sub.answer = {"text": text[: checker.MAX_ANSWER]}
        sub.status = CORRECT if checker.check_short(task, text) else INCORRECT
    elif task.type == CODE:
        code = answer.get("code") or ""
        if not code.strip():
            return None
        sub.answer, sub.status = {"code": code}, CHECKING
    else:
        text = (answer.get("text") or "").strip()
        if not text and not files:
            return None
        sub.answer, sub.files, sub.status = {"text": text}, files, PENDING_REVIEW
    if sub.status in (CORRECT, INCORRECT):
        sub.score, sub.checked_at = (1.0 if sub.status == CORRECT else 0.0), now
    return sub


async def finalize(session: AsyncSession, attempt: Attempt, a: Assignment, auto: bool) -> None:
    """Сдать попытку: черновики → отправки на проверку. Повторно сдать нельзя (ТЗ)."""
    if attempt.status != IN_PROGRESS:
        return
    now = datetime.now(UTC)
    tasks = {t.id: t for t in (await session.execute(select(Task).where(Task.id.in_([UUID(i) for i in attempt.task_order])))).scalars()}
    drafts = {d.task_id: d for d in (await session.execute(select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id))).scalars()}
    code_subs = []
    for task_id in attempt.task_order:
        task, draft = tasks.get(UUID(task_id)), drafts.get(UUID(task_id))
        if task is None or draft is None:
            continue
        sub = build_submission(task, draft.answer, draft.files, attempt.student_id, attempt.id, now)
        if sub is not None:
            session.add(sub)
            if sub.status == CHECKING:
                code_subs.append(sub)
    await session.flush()
    for sub in code_subs:
        await outbox.command(session, queue="assessment.code", type="assessment.code.check",
                             data={"submission_id": str(sub.id)}, actor_id=attempt.student_id)
    attempt.status, attempt.submitted_at, attempt.auto_submitted = SUBMITTED, now, auto
    await outbox.event(
        session, "assessment.attempt.submitted",
        {"attempt_id": str(attempt.id), "assignment_id": str(a.id), "student_id": str(attempt.student_id),
         "teacher_id": str(a.teacher_id), "title": a.title, "auto": auto},
        actor_id=None if auto else attempt.student_id,
    )
    await recompute(session, attempt, a)


def _earned(sub: Submission | None, points: int) -> float:
    if sub is None or sub.status in NOT_FINAL:
        return 0.0
    if sub.status == CORRECT:
        return float(points)
    if sub.status == REVIEWED:
        return round((sub.score or 0) * points, 2)
    return 0.0


async def latest_submissions(session: AsyncSession, attempt_id: UUID) -> dict[UUID, Submission]:
    subs = (await session.execute(
        select(Submission).where(Submission.context_type == "assignment", Submission.context_id == attempt_id)
        .order_by(Submission.created_at)
    )).scalars()
    return {s.task_id: s for s in subs}  # последняя (перепроверка создаёт не новую, а ту же отправку)


async def recompute(session: AsyncSession, attempt: Attempt, a: Assignment | None = None) -> None:
    """Пересчитать итог сданной попытки. Когда проверено всё — оценка и событие для журнала и уведомлений."""
    if attempt.status != SUBMITTED:
        return
    a = a or await session.get(Assignment, attempt.assignment_id)
    subs = await latest_submissions(session, attempt.id)
    points = {item["task_id"]: item["points"] for item in a.items}
    before = (attempt.checked, attempt.score, attempt.grade)
    attempt.max_score = float(sum(points.values()))
    attempt.score = round(sum(_earned(subs.get(UUID(t)), points.get(t, 1)) for t in attempt.task_order), 2)
    attempt.checked = not any(s.status in NOT_FINAL for s in subs.values())
    if attempt.checked:
        attempt.percent = round(attempt.score / attempt.max_score * 100, 1) if attempt.max_score else 0.0
        attempt.grade = grade_for(attempt.percent)
    else:
        attempt.percent = attempt.grade = None
    if attempt.checked and before != (attempt.checked, attempt.score, attempt.grade):
        await outbox.event(
            session, "assessment.attempt.graded",
            {"attempt_id": str(attempt.id), "assignment_id": str(a.id), "student_id": str(attempt.student_id),
             "teacher_id": str(a.teacher_id), "title": a.title, "kind": a.kind, "score": attempt.score,
             "max_score": attempt.max_score, "percent": attempt.percent, "grade": attempt.grade,
             "to_journal": a.grade_to_journal, "lesson_id": str(a.lesson_id) if a.lesson_id else None,
             "grade_type_id": str(a.grade_type_id) if a.grade_type_id else None},
        )


async def on_submission_changed(session: AsyncSession, sub: Submission) -> None:
    """Код проверен или педагог оценил развёрнутый ответ — обновить итог попытки."""
    if sub.context_type != "assignment":
        return
    attempt = await session.get(Attempt, sub.context_id, with_for_update=True)
    if attempt is not None:
        await recompute(session, attempt)


async def expire_job() -> None:
    """Фоновая задача: сдать попытки, у которых вышло время, наступил дедлайн или педагог завершил тест на уроке."""
    now = datetime.now(UTC)
    async with db.sessionmaker() as session, session.begin():
        rows = (await session.execute(
            select(Attempt, Assignment, AssignmentStudent)
            .join(Assignment, Assignment.id == Attempt.assignment_id)
            .join(AssignmentStudent, (AssignmentStudent.assignment_id == Attempt.assignment_id)
                  & (AssignmentStudent.student_id == Attempt.student_id))
            .where(
                Attempt.status == IN_PROGRESS,
                or_(
                    Attempt.ends_at < now - GRACE,
                    func.coalesce(AssignmentStudent.deadline, Assignment.deadline) < now - GRACE,
                    Assignment.closed_at.is_not(None),
                    Assignment.settings["time_mode"].astext == "per_task",
                ),
            )
            .with_for_update(of=Attempt, skip_locked=True)
            .limit(200)
        )).all()
        expired = 0
        for attempt, a, row in rows:
            if sync_timer(attempt, a, now, deadline_for(a, row)):
                await finalize(session, attempt, a, auto=True)
                expired += 1
    if expired:
        log.info("attempts expired", extra={"count": expired})
