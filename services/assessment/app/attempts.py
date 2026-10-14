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
    DEFAULT_GRADE_SCALE,
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
NOT_FINAL = (CHECKING, PENDING_REVIEW, ERROR)


def grade_for(percent: float, scale: dict[str, int] | None = None) -> int:
    """Процент → оценка по критериям работы (по умолчанию: от 85% — 5, от 65% — 4, от 45% — 3)."""
    scale = scale or DEFAULT_GRADE_SCALE
    return next((g for g in (5, 4, 3) if percent >= scale[str(g)]), 2)


def variant_of(a: Assignment, student_id) -> int | None:
    """Номер варианта ученика (решение №48); None — у работы нет вариантов."""
    if not a.variants:
        return None
    row = next((r for r in a.students if r.student_id == student_id), None)
    return row.variant if row is not None and row.variant else 1


def items_for(a: Assignment, student_id) -> list[dict]:
    """Состав работы для ученика — его варианта."""
    v = variant_of(a, student_id)
    return a.items if v is None else a.variants[v - 1]["items"]


def settings_for(a: Assignment, student_id) -> dict:
    """Настройки работы для ученика: у варианта — свои, как у его теста (таймер, порядок, оформление)."""
    v = variant_of(a, student_id)
    return a.settings if v is None else a.variants[v - 1].get("settings", a.settings)


def all_items(a: Assignment) -> list[dict]:
    return [i for v in a.variants for i in v["items"]] if a.variants else a.items


def needs_review(a: Assignment, student_id=None) -> bool:
    """К каким-то заданиям ученик прикладывает файл с решением — итог только после проверки педагогом.
    student_id — по варианту ученика, иначе по всем вариантам."""
    items = items_for(a, student_id) if student_id is not None else all_items(a)
    return any(item.get("solution_file") for item in items)


def solution_tasks(a: Assignment, student_id) -> set[str]:
    return {item["task_id"] for item in items_for(a, student_id) if item.get("solution_file")}


def per_task_limit(a: Assignment, student_id) -> timedelta | None:
    s = settings_for(a, student_id)
    return timedelta(seconds=s["time_limit_s"]) if s.get("time_mode") == "per_task" and s.get("time_limit_s") else None


def current_ends_at(attempt: Attempt, a: Assignment) -> datetime | None:
    limit = per_task_limit(a, attempt.student_id)
    if limit is None or attempt.current_started_at is None:
        return None
    return attempt.current_started_at + limit


def attempts_limit(a: Assignment, row: AssignmentStudent) -> int | None:
    """Сколько попыток у ученика: по настройке работы (переназначение добавляет); None — без ограничений."""
    return None if a.max_attempts is None else max(a.max_attempts, row.allowed_attempts)


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
    limit = per_task_limit(a, attempt.student_id)
    if limit is not None and attempt.current_started_at is not None:
        while now >= attempt.current_started_at + limit + GRACE:
            attempt.current_index += 1
            attempt.current_started_at += limit
            if attempt.current_index >= len(attempt.task_order):
                return True
    return False


def build_submission(task: Task, answer: dict, files: list[dict], student_id: UUID, attempt_id: UUID, now: datetime,
                     solution_file: bool = False) -> Submission | None:
    """Черновик → отправка. Пустой или некорректный ответ — не отправка: за задание 0 баллов.
    solution_file — к короткому ответу или выбору прикладывают файл с решением: он идёт в отправку для педагога,
    а файл без ответа — отправка с ответом «нет» (0 баллов, педагог может засчитать)."""
    sub = Submission(task_id=task.id, student_id=student_id, context_type="assignment", context_id=attempt_id, created_at=now)
    if task.type in (CHOICE, SHORT) and solution_file:
        sub.files = files
    if task.type == CHOICE:
        valid = {str(o.id) for o in task.options}
        chosen = {str(i) for i in answer.get("option_ids") or []}
        if not chosen or not chosen <= valid:
            return _files_only(sub, now) if sub.files else None
        sub.answer = {"option_ids": sorted(chosen)}
        sub.status = CORRECT if checker.check_choice(task, {UUID(i) for i in chosen}) else INCORRECT
    elif task.type == SHORT:
        text = (answer.get("text") or "").strip()
        if not text:
            return _files_only(sub, now) if sub.files else None
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


def _files_only(sub: Submission, now: datetime) -> Submission:
    sub.answer, sub.status, sub.score, sub.checked_at = {}, INCORRECT, 0.0, now
    return sub


async def finalize(session: AsyncSession, attempt: Attempt, a: Assignment, auto: bool, by_teacher: UUID | None = None) -> None:
    """Сдать попытку: черновики → отправки на проверку. Повторно сдать нельзя (ТЗ).
    by_teacher — педагог завершил досрочно (кто именно — в событии для аудита)."""
    if attempt.status != IN_PROGRESS:
        return
    now = datetime.now(UTC)
    tasks = {t.id: t for t in (await session.execute(select(Task).where(Task.id.in_([UUID(i) for i in attempt.task_order])))).scalars()}
    drafts = {d.task_id: d for d in (await session.execute(select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id))).scalars()}
    code_subs, with_file = [], solution_tasks(a, attempt.student_id)
    for task_id in attempt.task_order:
        task, draft = tasks.get(UUID(task_id)), drafts.get(UUID(task_id))
        if task is None or draft is None:
            continue
        sub = build_submission(task, draft.answer, draft.files, attempt.student_id, attempt.id, now, task_id in with_file)
        if sub is not None:
            session.add(sub)
            if sub.status == CHECKING:
                code_subs.append(sub)
    await session.flush()
    for sub in code_subs:
        await outbox.command(session, queue="assessment.code", type="assessment.code.check",
                             data={"submission_id": str(sub.id)}, actor_id=attempt.student_id)
    attempt.status, attempt.submitted_at, attempt.auto_submitted = SUBMITTED, now, auto
    attempt.finished_by_teacher = by_teacher is not None
    await outbox.event(
        session, "assessment.attempt.submitted",
        {"attempt_id": str(attempt.id), "assignment_id": str(a.id), "student_id": str(attempt.student_id),
         "teacher_id": str(a.teacher_id), "title": a.title, "auto": auto, "by_teacher": by_teacher is not None},
        actor_id=by_teacher or (None if auto else attempt.student_id),
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
    points = {item["task_id"]: item["points"] for item in items_for(a, attempt.student_id)}
    before = (attempt.checked, attempt.score, attempt.grade)
    attempt.max_score = float(sum(points.values()))
    attempt.score = round(sum(_earned(subs.get(UUID(t)), points.get(t, 1)) for t in attempt.task_order), 2)
    # С файлами решений итог — только после проверки педагогом, даже если всё проверилось автоматически.
    attempt.checked = not any(s.status in NOT_FINAL for s in subs.values()) and (attempt.reviewed_at is not None or not needs_review(a, attempt.student_id))
    if attempt.checked:
        attempt.percent = round(attempt.score / attempt.max_score * 100, 1) if attempt.max_score else 0.0
        attempt.grade = attempt.grade_override or grade_for(attempt.percent, a.grade_scale)
    else:
        attempt.percent = attempt.grade = None
    if attempt.checked and before != (attempt.checked, attempt.score, attempt.grade):
        # Попыток может быть несколько — в итог (журнал, уведомление) идёт лучшая (решение №15).
        await session.flush()
        checked = (await session.execute(
            select(Attempt).where(Attempt.assignment_id == a.id, Attempt.student_id == attempt.student_id,
                                  Attempt.status == SUBMITTED, Attempt.checked.is_(True))
        )).scalars().all()
        best = max(checked, key=lambda t: (t.grade or 0, t.percent or 0, t.submitted_at or t.started_at))
        # Журнал: оценка — в колонке работы (дата — когда назначена; для группы — в журнале группы).
        await outbox.event(
            session, "assessment.attempt.graded",
            {"attempt_id": str(best.id), "assignment_id": str(a.id), "student_id": str(attempt.student_id),
             "teacher_id": str(a.teacher_id), "title": a.title, "kind": a.kind, "score": best.score,
             "max_score": best.max_score, "percent": best.percent, "grade": best.grade, "attempts": len(checked),
             "by_teacher": best.grade_override is not None,
             "to_journal": a.grade_to_journal, "lesson_id": str(a.lesson_id) if a.lesson_id else None,
             "group_id": str(a.target_id) if a.target_type == "group" else None,
             "assigned_at": a.created_at.isoformat() if a.created_at else None,
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
                    Assignment.variants.is_not(None),  # у вариантов таймер свой — проверяет sync_timer
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
