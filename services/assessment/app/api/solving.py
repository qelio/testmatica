"""Решение задач учеником и просмотр решений педагогом."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import access, attempts, checker, views
from ..config import settings
from ..deps import auth, db, media, outbox
from ..models import (
    CHECKING,
    CHOICE,
    CODE,
    CORRECT,
    INCORRECT,
    LONG,
    PENDING_REVIEW,
    REVIEWED,
    SHORT,
    Submission,
    Task,
)
from ..schemas import ReviewIn, SolveView, SubmissionIn, SubmissionOut

router = APIRouter(tags=["solving"])


async def _file_urls(subs) -> dict[str, str]:
    ids = [f["id"] for s in subs for f in s.files]
    if not ids:
        return {}
    try:
        found = await media.post("/internal/files/urls", json={"file_ids": ids})
    except ApiError:
        return {}
    return {fid: f["url"] for fid, f in found.items()}


@router.get("/tasks/{task_id}/solve", response_model=SolveView)
async def solve_view(
    task_id: UUID,
    context_type: str = Query("practice", pattern="^(practice|assignment)$"),
    context_id: UUID = Query(),
    principal: Principal | None = Depends(auth.optional),
    session: AsyncSession = Depends(db.session),
) -> SolveView:
    """Задача глазами ученика + его попытки в этом контексте (модуль курса или ДЗ).
    Гость видит условие, решать может только после входа."""
    task = await access.viewable(session, task_id, principal)
    subs = []
    if principal is not None:
        subs = (
            await session.execute(
                select(Submission)
                .where(
                    Submission.task_id == task.id,
                    Submission.student_id == principal.user_id,
                    Submission.context_type == context_type,
                    Submission.context_id == context_id,
                )
                .order_by(Submission.created_at.desc())
            )
        ).scalars().all()
    solved = any(s.status == CORRECT or (s.status == REVIEWED and (s.score or 0) >= 0.5) for s in subs)
    finished = [s for s in subs if s.status != CHECKING]
    show_explanation = bool(task.explanation) and (solved or len(finished) >= settings.explanation_after_attempts)
    # Ученику — условие без ответов, даже если он педагог по другой роли: ключ отдаёт GET /tasks/{id}.
    view = await views.full(session, task, None)
    urls = await _file_urls(subs)
    return SolveView(
        task=view,
        submissions=[views.submission_out(s, with_log=False, urls=urls) for s in subs],
        solved=solved,
        explanation=task.explanation if show_explanation else None,
    )


@router.post("/tasks/{task_id}/submissions", response_model=SubmissionOut, status_code=201)
async def submit_answer(
    task_id: UUID,
    body: SubmissionIn,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> SubmissionOut:
    task = await access.viewable(session, task_id, principal)
    if body.context_type != "practice":
        raise ApiError(422, "use_attempt", "Ответы в тестах и ДЗ сохраняются в попытке и проверяются после сдачи")
    ans = body.answer
    now = datetime.now(UTC)
    sub = Submission(
        task_id=task.id, student_id=principal.user_id, context_type=body.context_type, context_id=body.context_id,
        created_at=now,
    )

    if task.type == CHOICE:
        valid = {o.id for o in task.options}
        chosen = set(ans.option_ids or [])
        if not chosen or not chosen <= valid:
            raise ApiError(422, "invalid_answer", "Выберите вариант ответа")
        sub.answer = {"option_ids": [str(i) for i in chosen]}
        sub.status = CORRECT if checker.check_choice(task, chosen) else INCORRECT
    elif task.type == SHORT:
        text = (ans.text or "").strip()
        if not text:
            raise ApiError(422, "invalid_answer", "Введите ответ")
        sub.answer = {"text": text[: checker.MAX_ANSWER]}
        sub.status = CORRECT if checker.check_short(task, text) else INCORRECT
    elif task.type == CODE:
        code = ans.code or ""
        if not code.strip():
            raise ApiError(422, "invalid_answer", "Напишите программу")
        last = await session.scalar(
            select(Submission.created_at)
            .where(Submission.student_id == principal.user_id, Submission.answer.has_key("code"))  # noqa: W601
            .order_by(Submission.created_at.desc())
            .limit(1)
        )
        if last and now - last < timedelta(seconds=settings.code_submit_interval_seconds):
            raise ApiError(429, "too_often", "Подождите пару секунд перед следующей отправкой")
        sub.answer = {"code": code}  # код сохраняется целиком в каждой попытке
        sub.status = CHECKING
    else:  # LONG
        text = (ans.text or "").strip()
        if task.file_mode == "required" and not body.file_ids:
            raise ApiError(422, "file_required", "К этой задаче нужно прикрепить файл с решением")
        if task.file_mode == "none" and body.file_ids:
            raise ApiError(422, "files_not_allowed", "К этой задаче нельзя прикрепить файл")
        if not text and not body.file_ids:
            raise ApiError(422, "invalid_answer", "Напишите ответ")
        if body.file_ids:
            claimed = await media.post(
                "/internal/files/claim",
                json={"owner_id": str(principal.user_id), "purpose": "answer", "file_ids": [str(i) for i in body.file_ids],
                      "claimed_by": "assessment"},
            )
            sub.files = [{k: f[k] for k in ("id", "filename", "mime", "size")} for f in claimed]
        sub.answer = {"text": text}
        sub.status = PENDING_REVIEW

    if sub.status in (CORRECT, INCORRECT):
        sub.score = 1.0 if sub.status == CORRECT else 0.0
        sub.checked_at = now
    session.add(sub)
    await session.flush()
    if task.type == CODE:
        # Проверка — асинхронно: песочница может быть занята; ответ клиенту сразу, статус «проверяется».
        await outbox.command(
            session, queue="assessment.code", type="assessment.code.check", data={"submission_id": str(sub.id)},
            actor_id=principal.user_id,
        )
    await outbox.event(
        session,
        "assessment.submission.created",
        {"submission_id": str(sub.id), "task_id": str(task.id), "student_id": str(principal.user_id),
         "context_type": sub.context_type, "context_id": str(sub.context_id), "status": sub.status, "type": task.type},
        actor_id=principal.user_id,
    )
    await session.commit()
    return views.submission_out(sub, with_log=False, urls=await _file_urls([sub]))


async def _visible_submission(session: AsyncSession, submission_id: UUID, principal: Principal) -> Submission:
    sub = await session.get(Submission, submission_id)
    if sub is None or not await access.can_see_student_work(session, principal, sub.student_id):
        raise ApiError(404, "submission_not_found", "Решение не найдено")
    return sub


@router.get("/submissions/{submission_id}", response_model=SubmissionOut)
async def get_submission(
    submission_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> SubmissionOut:
    """Статус проверки (ученик опрашивает, пока идёт прогон кода). Протокол прогона — только педагогу."""
    sub = await _visible_submission(session, submission_id, principal)
    return views.submission_out(sub, with_log=principal.user_id != sub.student_id, urls=await _file_urls([sub]))


@router.get("/students/{student_id}/submissions", response_model=list[SubmissionOut])
async def student_history(
    student_id: UUID,
    task_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(auth.require(ROLE_TEACHER)),
    session: AsyncSession = Depends(db.session),
) -> list[SubmissionOut]:
    """История решений ученика для его педагога — с кодом каждой попытки и протоколом прогона."""
    if not await access.linked(session, principal.user_id, student_id):
        raise ApiError(404, "student_not_found", "Ученик не привязан к вам")
    query = select(Submission).where(Submission.student_id == student_id)
    if task_id:
        query = query.where(Submission.task_id == task_id)
    subs = (await session.execute(query.order_by(Submission.created_at.desc()).limit(limit))).scalars().all()
    urls = await _file_urls(subs)
    tasks = {
        t.id: t
        for t in (await session.execute(select(Task).where(Task.id.in_({s.task_id for s in subs})))).scalars()
    } if subs else {}
    out = [views.submission_out(s, with_log=True, urls=urls) for s in subs]
    for item in out:
        if task := tasks.get(item.task_id):
            item.task_title, item.task_type = task.title, task.type
    return out


@router.post("/submissions/{submission_id}/review", response_model=SubmissionOut)
async def review(
    submission_id: UUID,
    body: ReviewIn,
    principal: Principal = Depends(auth.require(ROLE_TEACHER)),
    session: AsyncSession = Depends(db.session),
) -> SubmissionOut:
    """Проверка развёрнутого ответа педагогом ученика: оценка (доля от 0 до 1) и комментарий."""
    sub = await session.get(Submission, submission_id, with_for_update=True)
    if sub is None or not await access.linked(session, principal.user_id, sub.student_id):
        raise ApiError(404, "submission_not_found", "Решение не найдено")
    task = await access.load(session, sub.task_id)
    if task.type != LONG:
        raise ApiError(409, "auto_checked", "Это задание проверяется автоматически")
    sub.status, sub.score, sub.teacher_comment = REVIEWED, body.score, body.comment.strip()
    sub.reviewer_id, sub.reviewed_at = principal.user_id, datetime.now(UTC)
    await outbox.event(
        session,
        "assessment.submission.reviewed",
        {"submission_id": str(sub.id), "task_id": str(task.id), "task_title": task.title, "student_id": str(sub.student_id),
         "score": body.score, "comment": sub.teacher_comment, "context_type": sub.context_type, "context_id": str(sub.context_id)},
        actor_id=principal.user_id,
    )
    await attempts.on_submission_changed(session, sub)  # ответ из теста или ДЗ — пересчитать итог работы
    await session.commit()
    return views.submission_out(sub, with_log=True, urls=await _file_urls([sub]))
