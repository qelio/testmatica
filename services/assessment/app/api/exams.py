"""ЕГЭ и ОГЭ: каталог заданий, прогресс учеников по заданиям и отметки педагога («пройдено», примечания)."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_MODERATOR, ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import access, views
from ..deps import auth, classroom, db
from ..models import PUBLISHED, Exam, ExamItem, ExamMark, Task
from ..schemas import (
    BoardPerson,
    BoardRow,
    ExamBoard,
    ExamIn,
    ExamItemIn,
    ExamItemOut,
    ExamItemUpdate,
    ExamOut,
    ItemTaskProgress,
    MarkIn,
    Progress,
    StudentProgress,
)

router = APIRouter(tags=["exams"])
moderator = auth.require(ROLE_MODERATOR)
teacher = auth.require(ROLE_TEACHER)

# Решение засчитывается верным: автопроверка «верно» или проверка педагогом на 50% и выше.
_OK = "(s.status = 'correct' OR (s.status = 'reviewed' AND s.score >= 0.5))"
_FINISHED = "s.status IN ('correct', 'incorrect', 'reviewed')"


def _exam_out(e: Exam) -> ExamOut:
    return ExamOut(id=e.id, kind=e.kind, subject_id=e.subject_id, subject_name=e.subject_name, title=e.title,
                   items=[ExamItemOut(id=i.id, number=i.number, title=i.title) for i in e.items])


async def _exam(session: AsyncSession, exam_id: UUID) -> Exam:
    exam = await session.get(Exam, exam_id)
    if exam is None:
        raise ApiError(404, "exam_not_found", "Экзамен не найден")
    return exam


# ---------- каталог ----------


@router.get("/exams", response_model=list[ExamOut])
async def exams(_: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> list[ExamOut]:
    """Все экзамены с заданиями — для тегов задач, занятий и таблиц прогресса."""
    rows = (await session.execute(select(Exam).order_by(Exam.subject_name, Exam.kind, Exam.position))).scalars()
    return [_exam_out(e) for e in rows]


@router.post("/exams", response_model=ExamOut, status_code=201)
async def create_exam(body: ExamIn, _: Principal = Depends(moderator), session: AsyncSession = Depends(db.session)) -> ExamOut:
    exam = Exam(kind=body.kind, subject_id=body.subject_id, subject_name=body.subject_name, title=body.title, items=[])
    session.add(exam)
    await session.commit()
    return _exam_out(exam)


async def _item_in_use(session: AsyncSession, item_id: UUID) -> bool:
    return bool(await session.scalar(select(func.count()).select_from(Task).where(Task.exam_item_ids.contains([item_id]))))


@router.delete("/exams/{exam_id}", status_code=204)
async def delete_exam(exam_id: UUID, _: Principal = Depends(moderator), session: AsyncSession = Depends(db.session)) -> None:
    exam = await _exam(session, exam_id)
    if await session.scalar(select(func.count()).select_from(Task).where(Task.exam_item_ids.overlap([i.id for i in exam.items]))):
        raise ApiError(409, "exam_in_use", "К заданиям экзамена привязаны задачи — сначала уберите их")
    await session.delete(exam)
    await session.commit()


@router.post("/exams/{exam_id}/items", response_model=ExamItemOut, status_code=201)
async def add_item(
    exam_id: UUID, body: ExamItemIn, _: Principal = Depends(moderator), session: AsyncSession = Depends(db.session)
) -> ExamItemOut:
    exam = await _exam(session, exam_id)
    if any(i.number == body.number for i in exam.items):
        raise ApiError(409, "number_taken", f"Задание №{body.number} уже есть")
    item = ExamItem(exam_id=exam.id, number=body.number, title=body.title)
    session.add(item)
    await session.commit()
    return ExamItemOut(id=item.id, number=item.number, title=item.title)


@router.patch("/exam-items/{item_id}", response_model=ExamItemOut)
async def update_item(
    item_id: UUID, body: ExamItemUpdate, _: Principal = Depends(moderator), session: AsyncSession = Depends(db.session)
) -> ExamItemOut:
    item = await session.get(ExamItem, item_id, with_for_update=True)
    if item is None:
        raise ApiError(404, "exam_item_not_found", "Задание не найдено")
    if body.number is not None and body.number != item.number:
        taken = await session.scalar(select(ExamItem.id).where(ExamItem.exam_id == item.exam_id, ExamItem.number == body.number))
        if taken:
            raise ApiError(409, "number_taken", f"Задание №{body.number} уже есть")
        item.number = body.number
    if body.title is not None:
        item.title = body.title
    await session.commit()
    return ExamItemOut(id=item.id, number=item.number, title=item.title)


@router.delete("/exam-items/{item_id}", status_code=204)
async def delete_item(item_id: UUID, _: Principal = Depends(moderator), session: AsyncSession = Depends(db.session)) -> None:
    item = await session.get(ExamItem, item_id)
    if item is None:
        raise ApiError(404, "exam_item_not_found", "Задание не найдено")
    if await _item_in_use(session, item_id):
        raise ApiError(409, "exam_item_in_use", "К заданию привязаны задачи — сначала уберите их")
    await session.delete(item)
    await session.commit()


# ---------- доступ к ученику / группе ----------


async def _students(session: AsyncSession, p: Principal, target_type: str, target_id: UUID) -> tuple[list[UUID], bool]:
    """Ученики цели и может ли пользователь ставить отметки. Ученик видит только себя, педагог — своих."""
    if target_type == "student":
        if target_id == p.user_id:
            return [target_id], False
        if p.has_any(ROLE_TEACHER) and await access.linked(session, p.user_id, target_id):
            return [target_id], True
        raise ApiError(404, "student_not_found", "Ученик не привязан к вам")
    if not p.has_any(ROLE_TEACHER):
        raise ApiError(404, "group_not_found", "Группа не найдена")
    group = await classroom.get(f"/internal/groups/{target_id}", params={"teacher_id": str(p.user_id)})
    return [UUID(s) for s in group["member_ids"]], True


async def _progress(session: AsyncSession, students: list[UUID], item_ids: list[UUID]) -> dict[tuple[UUID, UUID], Progress]:
    """Прогресс (задание, ученик) по всем решениям ученика — в курсах, ДЗ, тестах."""
    if not students or not item_ids:
        return {}
    rows = await session.execute(
        text(f"""
            SELECT item_id, s.student_id,
                   count(DISTINCT s.task_id) AS attempted,
                   count(DISTINCT s.task_id) FILTER (WHERE {_OK}) AS solved,
                   count(*) AS attempts,
                   count(*) FILTER (WHERE {_OK}) AS correct_attempts,
                   max(s.created_at) AS last_at
            FROM submissions s
            JOIN tasks t ON t.id = s.task_id
            CROSS JOIN LATERAL unnest(t.exam_item_ids) AS item_id
            WHERE s.student_id = ANY(CAST(:students AS uuid[])) AND item_id = ANY(CAST(:items AS uuid[])) AND {_FINISHED}
            GROUP BY item_id, s.student_id
        """),
        {"students": [str(s) for s in students], "items": [str(i) for i in item_ids]},
    )
    return {(r.item_id, r.student_id): Progress(attempted=r.attempted, solved=r.solved, attempts=r.attempts,
                                                  correct_attempts=r.correct_attempts, last_at=r.last_at) for r in rows}


def _sum(parts: list[Progress]) -> Progress:
    last = [p.last_at for p in parts if p.last_at]
    return Progress(
        attempted=sum(p.attempted for p in parts), solved=sum(p.solved for p in parts), attempts=sum(p.attempts for p in parts),
        correct_attempts=sum(p.correct_attempts for p in parts), last_at=max(last) if last else None,
    )


STAGES = ("theory", "practice", "control")  # этапы работы с заданием: материал, практика, контроль


@router.get("/exam-board", response_model=ExamBoard)
async def board(
    exam_id: UUID,
    target_type: str = Query(pattern="^(student|group)$"),
    target_id: UUID = Query(),
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> ExamBoard:
    """Таблица заданий экзамена для ученика или группы: отметки педагога и прогресс по решённым задачам."""
    exam = await _exam(session, exam_id)
    students, can_edit = await _students(session, principal, target_type, target_id)
    item_ids = [i.id for i in exam.items]
    progress = await _progress(session, students, item_ids)

    marks_q = select(ExamMark).where(ExamMark.target_type == target_type, ExamMark.target_id == target_id,
                                     ExamMark.item_id.in_(item_ids))
    if can_edit:
        marks_q = marks_q.where(ExamMark.teacher_id == principal.user_id)
    # Ученик видит отметки всех своих педагогов: этап отмечен, если его отметил хоть один.
    marks: dict[UUID, dict] = {}
    for m in (await session.execute(marks_q.order_by(ExamMark.updated_at))).scalars():
        cur = marks.setdefault(m.item_id, {"theory": False, "practice": False, "control": False, "done": False,
                                           "done_at": None, "note": ""})
        for f in STAGES + ("done",):
            cur[f] = cur[f] or getattr(m, f)
        if m.done and (cur["done_at"] is None or (m.done_at and m.done_at < cur["done_at"])):
            cur["done_at"] = m.done_at
        cur["note"] = m.note

    in_bank = dict((await session.execute(
        text("""
            SELECT item_id, count(*) FROM tasks CROSS JOIN LATERAL unnest(exam_item_ids) AS item_id
            WHERE status = :published AND item_id = ANY(CAST(:items AS uuid[])) GROUP BY item_id
        """),
        {"published": PUBLISHED, "items": [str(i) for i in item_ids]},
    )).all())
    names = await views.names(session, students)

    rows = []
    for item in exam.items:
        per = [StudentProgress(student_id=s, **progress.get((item.id, s), Progress()).model_dump()) for s in students]
        mark = marks.get(item.id) or {}
        rows.append(BoardRow(
            item_id=item.id, number=item.number, title=item.title,
            **{f: mark.get(f, False) for f in STAGES + ("done",)},
            done_at=mark.get("done_at"), note=mark.get("note", "") if can_edit else None,
            progress=_sum(per), by_student=per if target_type == "group" else [], tasks_in_bank=in_bank.get(item.id, 0),
        ))
    return ExamBoard(
        exam=_exam_out(exam), target_type=target_type, target_id=target_id, can_edit=can_edit, rows=rows,
        students=sorted((BoardPerson(id=s, full_name=names.get(s, "Ученик")) for s in students), key=lambda p: p.full_name),
    )


@router.put("/exam-marks", status_code=204)
async def set_mark(body: MarkIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> None:
    """Этапы (материал, практика, контроль), «пройдено» и примечание — для своего ученика или своей группы.
    Меняются только переданные поля."""
    _, can_edit = await _students(session, principal, body.target_type, body.target_id)
    if not can_edit:
        raise ApiError(403, "forbidden", "Отметки ставит педагог")
    if await session.get(ExamItem, body.item_id) is None:
        raise ApiError(404, "exam_item_not_found", "Задание не найдено")
    now = datetime.now(UTC)
    given = body.model_dump(include={*STAGES, "done", "note"}, exclude_none=True)
    if "note" in given:
        given["note"] = given["note"].strip()
    stmt = insert(ExamMark).values(
        teacher_id=principal.user_id, target_type=body.target_type, target_id=body.target_id, item_id=body.item_id,
        **given, done_at=now if given.get("done") else None, updated_at=now,
    )
    update = {f: getattr(stmt.excluded, f) for f in given} | {"updated_at": now}
    if "done" in given:
        # Дата «пройдено» не сдвигается при повторной отметке.
        update["done_at"] = func.coalesce(ExamMark.done_at, stmt.excluded.done_at) if given["done"] else None
    await session.execute(stmt.on_conflict_do_update(constraint="uq_exam_marks_target_item", set_=update))
    await session.commit()


@router.get("/exam-board/tasks", response_model=list[ItemTaskProgress])
async def item_tasks(
    student_id: UUID,
    item_id: UUID,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> list[ItemTaskProgress]:
    """Задачи ученика по одному заданию экзамена: сколько попыток, решена ли, чем закончилась последняя."""
    await _students(session, principal, "student", student_id)
    rows = await session.execute(
        text(f"""
            SELECT t.id, t.title, t.type, count(*) AS attempts, bool_or({_OK}) AS solved,
                   (array_agg(s.status ORDER BY s.created_at DESC))[1] AS last_status, max(s.created_at) AS last_at
            FROM submissions s JOIN tasks t ON t.id = s.task_id
            WHERE s.student_id = :student AND :item = ANY(t.exam_item_ids) AND {_FINISHED}
            GROUP BY t.id, t.title, t.type
            ORDER BY max(s.created_at) DESC
        """),
        {"student": student_id, "item": item_id},
    )
    return [ItemTaskProgress(task_id=r.id, title=r.title, type=r.type, attempts=r.attempts, solved=r.solved,
                             last_status=r.last_status, last_at=r.last_at) for r in rows]
