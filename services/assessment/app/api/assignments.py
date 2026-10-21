"""Назначение тестов (просто тест, на дом, на уроке) и их прохождение учениками."""

import random
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_MODERATOR, ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError
from testmatica_common.plans import BASIC

from .. import access, attempts, class_access, sharing, views
from ..deps import auth, classroom, db, media, outbox, plans, schedule
from ..models import (
    CHECKING,
    CODE,
    CODE_LIVE,
    CHOICE,
    CORRECT,
    ERROR,
    INCORRECT,
    IN_PROGRESS,
    LIVE,
    LONG,
    PROCTOR_ALERTS,
    REVIEWED,
    SELF,
    SUBMITTED,
    Assignment,
    AssignmentStudent,
    Attempt,
    AttemptAnswer,
    ProctorEvent,
    Submission,
    Task,
    Test,
)
from ..schemas import (
    AssignIn,
    AssignmentOut,
    AssignmentPart,
    AssignmentPartItem,
    AssignmentStudentOut,
    AssignmentTarget,
    AssignmentUpdate,
    AttemptBrief,
    AttemptOut,
    AttemptReviewIn,
    AttemptStatusOut,
    AttemptTask,
    CodeCheckIn,
    CodeCheckOut,
    DraftIn,
    FileRef,
    ModuleRef,
    ProctorEventIn,
    ProctorEventOut,
    RemovedOut,
    RemoveStudentsIn,
    StartIn,
    SubmissionOut,
    VariantOut,
    VariantSet,
)
from ..courses import course_test_for, module_info
from .quizzes import own_test
from .solving import _file_urls

router = APIRouter(tags=["assignments"])
teacher = auth.require(ROLE_TEACHER, ROLE_MODERATOR)


# ---------- выдача ----------


async def assignable_test(session: AsyncSession, test_id: UUID, p: Principal) -> Test:
    """Назначить можно свой тест или тест автора курса — публичный или «для педагогов», принятый вместе с курсом,
    если педагог видит курс (решения №44, 46)."""
    test = await session.get(Test, test_id)
    if await sharing.share_of(session, test, p) is not None:  # тестом поделился коллега (решение №58)
        return test
    if test is not None and test.owner_id != p.user_id and await course_test_for(session, test, p) is not None:
        return test
    return await own_test(session, test_id, p)


async def test_theme(test: Test, user_id: UUID) -> str:
    """Оформление работы: тест привязан к модулю — текущая тема курса, иначе обычное (решения №42, 44)."""
    if not test.module_id:
        return "classic"
    module = await module_info(test.module_id, user_id)
    return module["course_theme"] if module else "classic"


def copy_of(test: Test, theme: str) -> dict:
    """Состав и настройки теста на момент выдачи — правка теста выданное не меняет."""
    return {
        "test_id": test.id, "test_title": test.title, "grade_level": test.grade_level, "description": test.description,
        "subject_id": test.subject_id, "subject_name": test.subject_name,
        "module_id": test.module_id, "course_id": test.course_id, "module_title": test.module_title,
        "settings": {"order_mode": test.order_mode, "shuffle_options": test.shuffle_options, "time_mode": test.time_mode,
                     "time_limit_s": test.time_limit_s, "theme": theme},
        "items": [{"task_id": str(i.task_id), "points": i.points, "solution_file": i.solution_file, "code_check": i.code_check}
                  for i in test.items],
    }


def distribute(student_ids: list[UUID], count: int, manual: dict[UUID, int]) -> dict[UUID, int]:
    """Варианты ученикам (решение №48): заданные вручную — как есть, остальным — поровну и вперемешку."""
    out = {s: manual[s] for s in student_ids if s in manual}
    used = [0] * count
    for v in out.values():
        used[v - 1] += 1
    rnd = random.SystemRandom()
    rest = [s for s in student_ids if s not in out]
    rnd.shuffle(rest)
    for s in rest:
        fewest = min(used)
        v = rnd.choice([i for i, n in enumerate(used) if n == fewest])
        used[v] += 1
        out[s] = v + 1
    return out


@router.post("/tests/{test_id}/assign", response_model=AssignmentOut, status_code=201)
async def assign(
    test_id: UUID, body: AssignIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> AssignmentOut:
    """Назначить тест группе или ученику: просто тест, на дом (к уроку) или на уроке. Состав теста фиксируется."""
    test = await assignable_test(session, test_id, principal)
    if not test.items:
        raise ApiError(422, "test_empty", "Добавьте в тест хотя бы одну задачу")
    if body.target_type == "group":
        group = await classroom.get(f"/internal/groups/{body.target_id}", params={"teacher_id": str(principal.user_id)})
        student_ids, target_title = [UUID(s) for s in group["member_ids"]], group["title"]
        if not student_ids:
            raise ApiError(422, "group_empty", "В группе нет учеников")
    else:
        if not await access.linked(session, principal.user_id, body.target_id):
            raise ApiError(404, "student_not_found", "Ученик не привязан к вам")
        student_ids = [body.target_id]
        target_title = (await views.names(session, student_ids)).get(body.target_id, "Ученик")
    if body.lesson_id:
        await schedule.get(f"/internal/lessons/{body.lesson_id}", params={"teacher_id": str(principal.user_id)})
    if body.deadline and body.deadline <= datetime.now(UTC):
        raise ApiError(422, "deadline_past", "Дедлайн уже прошёл")
    if body.proctoring and await plans.of(principal.user_id) != BASIC:
        raise ApiError(403, "plan_required", "Прокторинг доступен на тарифе «Базовый»")

    theme = await test_theme(test, principal.user_id)
    # Варианты: тесты 2-го, 3-го… вариантов; у каждого ученика — свой (решение №48).
    variant_tests = [test]
    for vid in body.variant_test_ids:
        if vid == test.id:
            raise ApiError(422, "variant_duplicate", "Один тест выбран в нескольких вариантах")
        vt = await assignable_test(session, vid, principal)
        if not vt.items:
            raise ApiError(422, "test_empty", f"В тесте «{vt.title}» нет задач")
        variant_tests.append(vt)
    numbers, variants = {}, None
    if len(variant_tests) > 1:
        numbers = distribute(student_ids, len(variant_tests), body.variants)
        # У каждого варианта — свои состав и настройки (таймер, порядок, оформление), как у его теста.
        variants = []
        for vt in variant_tests:
            copy = copy_of(vt, theme if vt is test else await test_theme(vt, principal.user_id))
            variants.append({"test_id": str(vt.id), "test_title": vt.title, "items": copy["items"], "settings": copy["settings"]})

    a = Assignment(
        **copy_of(test, theme), teacher_id=principal.user_id, title=body.title or test.title, kind=body.kind,
        target_type=body.target_type, target_id=body.target_id, target_title=target_title, lesson_id=body.lesson_id,
        opens_at=body.opens_at, deadline=body.deadline, max_attempts=body.max_attempts,
        grade_scale=body.grade_scale.stored(),
        grade_to_journal=body.grade_to_journal, grade_type_id=body.grade_type_id if body.grade_to_journal else None,
        proctoring=body.proctoring, variants=variants, result_after_review=body.result_after_review,
        students=[AssignmentStudent(student_id=s, allowed_attempts=body.max_attempts or 1, variant=numbers.get(s)) for s in student_ids],
    )
    session.add(a)
    await session.flush()
    await outbox.event(
        session, "assessment.assignment.created",
        {"assignment_id": str(a.id), "title": a.title, "kind": a.kind, "teacher_id": str(a.teacher_id),
         "student_ids": [str(s) for s in student_ids], "deadline": a.deadline.isoformat() if a.deadline else None,
         "opens_at": a.opens_at.isoformat() if a.opens_at else None,
         "lesson_id": str(a.lesson_id) if a.lesson_id else None},
        actor_id=principal.user_id,
    )
    await session.commit()
    return await assignment_out(session, a, principal, teacher_view=True)


async def _answered(session: AsyncSession, attempt_ids: list[UUID]) -> dict[UUID, int]:
    if not attempt_ids:
        return {}
    rows = await session.execute(
        select(AttemptAnswer.attempt_id, func.count()).where(AttemptAnswer.attempt_id.in_(attempt_ids)).group_by(AttemptAnswer.attempt_id)
    )
    return dict(rows.all())


async def _correct(session: AsyncSession, attempt_ids: list[UUID]) -> dict[UUID, int]:
    """Сколько заданий решено верно в каждой сданной попытке (развёрнутый ответ — если оценён полностью)."""
    if not attempt_ids:
        return {}
    rows = await session.execute(
        select(Submission.context_id, func.count(func.distinct(Submission.task_id)))
        .where(Submission.context_type == "assignment", Submission.context_id.in_(attempt_ids),
               (Submission.status == CORRECT) | ((Submission.status == REVIEWED) & (Submission.score >= 1)))
        .group_by(Submission.context_id)
    )
    return dict(rows.all())


def _brief(t: Attempt, answered: int, correct: dict[UUID, int] | None = None, a: Assignment | None = None) -> AttemptBrief:
    return AttemptBrief(
        id=t.id, number=t.number, status=t.status, started_at=t.started_at, submitted_at=t.submitted_at,
        auto_submitted=t.auto_submitted, finished_by_teacher=t.finished_by_teacher, screen_sharing=t.screen_sharing,
        answered=answered, total=len(t.task_order),
        correct=correct.get(t.id, 0) if correct is not None and t.status == SUBMITTED else None,
        ends_at=t.ends_at if t.status == IN_PROGRESS else None,
        current_ends_at=attempts.current_ends_at(t, a) if a is not None and t.status == IN_PROGRESS else None, score=t.score, max_score=t.max_score,
        percent=t.percent, grade=t.grade, checked=t.checked,
    )


async def _sync_open(session: AsyncSession, a: Assignment, rows: list[Attempt]) -> None:
    """Сдать просроченные попытки при просмотре — не дожидаясь фоновой задачи."""
    now = datetime.now(UTC)
    by_student = {r.student_id: r for r in a.students}
    for t in rows:
        if t.status == IN_PROGRESS and attempts.sync_timer(t, a, now, attempts.deadline_for(a, by_student.get(t.student_id))):
            await attempts.finalize(session, t, a, auto=True)


async def assignment_out(session: AsyncSession, a: Assignment, p: Principal, teacher_view: bool) -> AssignmentOut:
    now = datetime.now(UTC)
    rows = a.students if teacher_view else [r for r in a.students if r.student_id == p.user_id]
    query = select(Attempt).where(Attempt.assignment_id == a.id).order_by(Attempt.number)
    if not teacher_view:
        query = query.where(Attempt.student_id == p.user_id)
    all_attempts = (await session.execute(query)).scalars().all()
    await _sync_open(session, a, list(all_attempts))
    answered = await _answered(session, [t.id for t in all_attempts])
    # Педагогу — сколько верно у каждой сданной попытки; ученику — только когда работа проверена.
    correct = await _correct(session, [t.id for t in all_attempts if t.status == SUBMITTED and (teacher_view or t.checked)])
    alerts: dict[UUID, int] = {}
    if a.proctoring and teacher_view:
        alerts = dict((await session.execute(
            select(ProctorEvent.student_id, func.count()).where(ProctorEvent.assignment_id == a.id, ProctorEvent.kind.in_(PROCTOR_ALERTS))
            .group_by(ProctorEvent.student_id)
        )).all())
    names = await views.names(session, [r.student_id for r in rows] + [a.teacher_id] + ([a.target_id] if a.target_type == "student" else []))
    students = sorted(
        (
            AssignmentStudentOut(
                student_id=r.student_id, full_name=names.get(r.student_id, "Ученик"), allowed_attempts=r.allowed_attempts,
                variant=attempts.variant_of(a, r.student_id),
                attempts=[_brief(t, answered.get(t.id, 0), correct if teacher_view or t.checked else None, a)
                          for t in all_attempts if t.student_id == r.student_id],
                proctor_alerts=alerts.get(r.student_id, 0),
            )
            for r in rows
        ),
        key=lambda s: s.full_name,
    )
    own = rows[0] if rows and not teacher_view else None
    items = attempts.items_for(a, p.user_id) if own is not None else a.items  # ученику — его вариант
    deadline = attempts.deadline_for(a, own) if own else a.deadline
    not_open_yet = bool(a.opens_at and now < a.opens_at)
    can_start, attempts_left = False, None
    if own is not None:
        mine = [t for t in all_attempts if t.student_id == p.user_id]
        limit = attempts.attempts_limit(a, own)
        attempts_left = None if limit is None else max(0, limit - len(mine))
        can_start = (
            a.closed_at is None and not not_open_yet and not (deadline and now >= deadline)
            and not any(t.status == IN_PROGRESS for t in mine) and (limit is None or len(mine) < limit)
        )
    return AssignmentOut(
        id=a.id, test_id=a.test_id, title=a.title, test_title=a.test_title, grade_level=a.grade_level,
        description=a.description, kind=a.kind,
        proctoring=a.proctoring, target_type=a.target_type,
        target_id=a.target_id, teacher_id=a.teacher_id, teacher_view=teacher_view,
        # Ученику — текущее имя из реплики («Фамилия Имя»), а не копия на момент выдачи.
        target_title=names.get(a.target_id, a.target_title) if a.target_type == "student" else a.target_title,
        teacher_name=names.get(a.teacher_id, "Педагог"), lesson_id=a.lesson_id, opens_at=a.opens_at,
        module=ModuleRef(id=a.module_id, title=a.module_title or "", course_id=a.course_id) if a.module_id else None,
        deadline=deadline, not_open_yet=not_open_yet, overdue=bool(deadline and now >= deadline), closed=a.closed_at is not None,
        max_attempts=a.max_attempts, attempts_left=attempts_left,
        settings=attempts.settings_for(a, p.user_id) if own is not None else a.settings,
        tasks_count=len(items), max_score=sum(i["points"] for i in items), grade_scale=a.grade_scale,
        variants=[
            VariantOut(number=n, test_id=v["test_id"], test_title=v["test_title"], tasks_count=len(v["items"]),
                       max_score=sum(i["points"] for i in v["items"]), settings=v.get("settings", a.settings))
            for n, v in enumerate(a.variants, 1)
        ] if a.variants and teacher_view else None,
        needs_review=attempts.needs_review(a, None if teacher_view else p.user_id), result_after_review=a.result_after_review,
        grade_to_journal=a.grade_to_journal,
        grade_type_id=a.grade_type_id, created_at=a.created_at, students=students, can_start=can_start, server_time=now,
    )


@router.get("/assignments", response_model=list[AssignmentOut])
async def list_assignments(
    role: str = Query("student", pattern="^(teacher|student)$"),
    scope: str = Query("mine", pattern="^(mine|classes)$",
                       description="Педагогу: mine — выданные им; classes — работы его классов, выданные другими (решение №61)"),
    lesson_id: UUID | None = None,
    target_id: UUID | None = None,
    module_id: UUID | None = Query(None, description="Работы по модулю курса — для страницы модуля"),
    grade_level: str | None = Query(None, pattern=r"^(none|\d{1,2})$", description="Класс теста; none — класс не указан"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100, description="Постранично: запросите на одну больше, чтобы узнать, есть ли ещё"),
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> list[AssignmentOut]:
    """Педагогу — выданные им работы (scope=mine) или работы его классов, выданные другими педагогами (scope=classes:
    свои классы и общие с правом «Работы класса», решение №61); ученику — выданные ему. Новые — первыми, постранично."""
    as_teacher = role == "teacher"
    if as_teacher:
        if not principal.has_any(ROLE_TEACHER, ROLE_MODERATOR):
            raise ApiError(403, "forbidden", "Недостаточно прав")
        if scope == "classes":
            groups = await class_access.work_groups(principal.user_id) if principal.has_any(ROLE_TEACHER) else []
            query = select(Assignment).where(Assignment.teacher_id != principal.user_id, Assignment.target_type == "group",
                                             Assignment.target_id.in_(groups))
        else:
            query = select(Assignment).where(Assignment.teacher_id == principal.user_id)
    else:
        query = select(Assignment).join(AssignmentStudent).where(AssignmentStudent.student_id == principal.user_id)
    query = query.where(Assignment.kind != SELF)  # самостоятельные — под модулем курса и в карточке ученика
    if lesson_id:
        query = query.where(Assignment.lesson_id == lesson_id)
    if target_id:
        query = query.where(Assignment.target_id == target_id)
    if module_id:
        query = query.where(Assignment.module_id == module_id)
    if grade_level:
        query = query.where(Assignment.grade_level.is_(None) if grade_level == "none" else Assignment.grade_level == int(grade_level))
    query = query.order_by(Assignment.created_at.desc(), Assignment.id.desc()).offset(offset).limit(limit)
    found = (await session.execute(query)).scalars().all()
    out = [await assignment_out(session, a, principal, as_teacher) for a in found]
    await session.commit()  # просроченные попытки могли сдаться при просмотре
    return out


@router.get("/assignments/classes", response_model=list[AssignmentTarget])
async def work_classes(principal: Principal = Depends(teacher)) -> list[AssignmentTarget]:
    """Классы, работы которых педагог ведёт (свои и общие с правом «Работы класса», решение №61) — для раздела
    «Работы классов»."""
    rows = await class_access.work_classes(principal.user_id)
    return sorted((AssignmentTarget(target_type="group", target_id=g["id"], target_title=g["title"]) for g in rows),
                  key=lambda x: x.target_title.lower())


@router.get("/assignments/targets", response_model=list[AssignmentTarget])
async def assignment_targets(principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> list[AssignmentTarget]:
    """Кому педагог назначал работы — для фильтра списка (группы и ученики)."""
    rows = (await session.execute(
        select(Assignment.target_type, Assignment.target_id, func.max(Assignment.target_title))
        .where(Assignment.teacher_id == principal.user_id, Assignment.kind != SELF)
        .group_by(Assignment.target_type, Assignment.target_id)
    )).all()
    names = await views.names(session, [r[1] for r in rows if r[0] == "student"])
    return sorted(
        (AssignmentTarget(target_type=t, target_id=i, target_title=names.get(i, title) if t == "student" else title) for t, i, title in rows),
        key=lambda x: (x.target_type, x.target_title.lower()),
    )


async def _self_viewer(session: AsyncSession, a: Assignment, student_id: UUID, p: Principal, write: bool) -> bool | None:
    """Самостоятельная работа (решение №44): владелец — сам ученик; его педагоги только смотрят."""
    if student_id == p.user_id:
        return False
    if not write and await access.linked(session, p.user_id, student_id):
        return True
    return None


async def _assignment(session: AsyncSession, assignment_id: UUID, p: Principal, write: bool = False) -> tuple[Assignment, bool]:
    """Работа и роль смотрящего: педагог-автор, педагог класса с правом «Работы класса» (решение №61) или ученик,
    которому выдано. write — действие педагога."""
    a = await session.get(Assignment, assignment_id)
    if a is not None and a.kind == SELF:
        role = await _self_viewer(session, a, a.target_id, p, write)
        if role is not None:
            return a, role
    elif a is not None:
        if a.teacher_id == p.user_id:
            return a, True
        if any(r.student_id == p.user_id for r in a.students):
            return a, False
        if await class_access.can_run(a, p):
            return a, True
    raise ApiError(404, "assignment_not_found", "Задание не найдено")


@router.put("/assignments/{assignment_id}/students/{student_id}/variant", response_model=AssignmentOut)
async def set_variant(
    assignment_id: UUID, student_id: UUID, body: VariantSet, principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> AssignmentOut:
    """Поменять ученику вариант (решение №48) — пока он не начал работу."""
    a, is_teacher = await _assignment(session, assignment_id, principal, write=True)
    if not is_teacher or a.kind == SELF:
        raise ApiError(404, "assignment_not_found", "Задание не найдено")
    if not a.variants or body.variant > len(a.variants):
        raise ApiError(422, "variant_invalid", "Такого варианта в работе нет")
    row = next((r for r in a.students if r.student_id == student_id), None)
    if row is None:
        raise ApiError(404, "student_not_found", "Ученику эта работа не выдана")
    started = await session.scalar(
        select(func.count()).select_from(Attempt).where(Attempt.assignment_id == a.id, Attempt.student_id == student_id)
    )
    if started:
        raise ApiError(409, "variant_locked", "Ученик уже начал работу — вариант не поменять")
    row.variant = body.variant
    await session.commit()
    return await assignment_out(session, a, principal, teacher_view=True)


@router.get("/assignments/{assignment_id}", response_model=AssignmentOut)
async def get_assignment(
    assignment_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> AssignmentOut:
    """Педагогу — сводка по ученикам (на уроке — прогресс в реальном времени), ученику — его попытки."""
    a, is_teacher = await _assignment(session, assignment_id, principal)
    out = await assignment_out(session, a, principal, is_teacher)
    await session.commit()
    return out


@router.post("/assignments/{assignment_id}/reassign", response_model=AssignmentOut)
async def reassign(
    assignment_id: UUID,
    student_id: UUID = Query(),
    deadline: datetime | None = Query(None, description="Новый личный дедлайн"),
    principal: Principal = Depends(teacher),
    session: AsyncSession = Depends(db.session),
) -> AssignmentOut:
    """Переназначить ученику: ещё одна попытка. Все прошлые попытки сохраняются."""
    a, is_teacher = await _assignment(session, assignment_id, principal, write=True)
    if not is_teacher:
        raise ApiError(404, "assignment_not_found", "Задание не найдено")
    row = next((r for r in a.students if r.student_id == student_id), None)
    if row is None:
        raise ApiError(404, "student_not_found", "Этому ученику задание не выдавалось")
    tried = (await session.execute(select(Attempt).where(Attempt.assignment_id == a.id, Attempt.student_id == student_id))).scalars().all()
    if any(t.status == IN_PROGRESS for t in tried):
        raise ApiError(409, "attempt_in_progress", "Ученик ещё проходит тест")
    if deadline is not None and (deadline.tzinfo is None or deadline <= datetime.now(UTC)):
        raise ApiError(422, "deadline_past", "Укажите будущий дедлайн с часовым поясом")
    if a.max_attempts is not None:
        row.allowed_attempts = max(row.allowed_attempts, len(tried) + 1)
    row.deadline = deadline
    if a.kind == LIVE:
        a.closed_at = None
    await outbox.event(
        session, "assessment.assignment.reassigned",
        {"assignment_id": str(a.id), "title": a.title, "kind": a.kind, "teacher_id": str(a.teacher_id),
         "student_id": str(student_id), "deadline": deadline.isoformat() if deadline else None},
        actor_id=principal.user_id,
    )
    await session.commit()
    return await assignment_out(session, a, principal, teacher_view=True)


async def _drop_attempts(session: AsyncSession, a: Assignment, student_ids: set[UUID] | None) -> None:
    """Удалить попытки (с ответами и отправками) — всех учеников или перечисленных."""
    query = select(Attempt).where(Attempt.assignment_id == a.id)
    if student_ids is not None:
        query = query.where(Attempt.student_id.in_(student_ids))
    tried = (await session.execute(query)).scalars().all()
    if tried:
        # Отправки работы и проверки кода по кнопке (решение №49) — вместе с попытками.
        await session.execute(delete(Submission).where(Submission.context_type.in_(("assignment", "check")),
                                                       Submission.context_id.in_([t.id for t in tried])))
        for t in tried:
            await session.delete(t)


@router.get("/assignments/{assignment_id}/parts", response_model=list[AssignmentPart])
async def assignment_parts(
    assignment_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> list[AssignmentPart]:
    """Педагогу — задания выданной работы с баллами по вариантам и баллы в тестах сейчас (для правки, решение №52)."""
    a, is_teacher = await _assignment(session, assignment_id, principal)
    if not is_teacher or a.kind == SELF:
        raise ApiError(404, "assignment_not_found", "Задание не найдено")
    parts = [(n, UUID(v["test_id"]), v["test_title"], v["items"]) for n, v in enumerate(a.variants, 1)] if a.variants \
        else [(None, a.test_id, a.test_title, a.items)]
    ids = {UUID(i["task_id"]) for *_, items in parts for i in items}
    tasks = {t.id: t for t in (await session.execute(select(Task).where(Task.id.in_(ids)))).scalars()}
    tests = {t.id: t for t in (await session.execute(select(Test).where(Test.id.in_([p[1] for p in parts])))).scalars()}
    out = []
    for variant, test_id, title, items in parts:
        now = {str(i.task_id): i.points for i in tests[test_id].items} if test_id in tests else {}
        out.append(AssignmentPart(
            variant=variant, test_id=test_id, test_title=title,
            items=[AssignmentPartItem(task_id=i["task_id"], number=tasks[UUID(i["task_id"])].number,
                                      title=tasks[UUID(i["task_id"])].title, points=i["points"])
                   for i in items if UUID(i["task_id"]) in tasks],
            test_points=[now.get(i["task_id"]) for i in items if UUID(i["task_id"]) in tasks],
        ))
    return out


@router.patch("/assignments/{assignment_id}", response_model=AssignmentOut)
async def update_assignment(
    assignment_id: UUID, body: AssignmentUpdate, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> AssignmentOut:
    """Изменить выданную работу (решение №52): название, сроки, попытки, критерии, баллы за задания, «результаты после
    проверки». Баллы, критерии и «результаты после проверки» пересчитывают сданные попытки — оценки в журнале обновятся;
    оценки, поставленные педагогом вручную, не меняются."""
    a, is_teacher = await _assignment(session, assignment_id, principal, write=True)
    if not is_teacher or a.kind == SELF:
        raise ApiError(404, "assignment_not_found", "Задание не найдено")
    sent = body.model_fields_set
    if body.title is not None:
        a.title = body.title
    if "opens_at" in sent:
        a.opens_at = body.opens_at
    if "deadline" in sent:
        a.deadline = body.deadline
    if a.opens_at and a.deadline and a.deadline <= a.opens_at:
        raise ApiError(422, "deadline_before_open", "Тест должен закрываться позже, чем откроется")
    if "max_attempts" in sent:
        a.max_attempts = body.max_attempts
    recount = False
    if body.grade_scale is not None and body.grade_scale.stored() != a.grade_scale:
        a.grade_scale, recount = body.grade_scale.stored(), True
    if body.result_after_review is not None and body.result_after_review != a.result_after_review:
        a.result_after_review, recount = body.result_after_review, True

    # Баллы — по вариантам: у каждого свой список по порядку заданий.
    lists = [v["items"] for v in a.variants] if a.variants else [a.items]
    if body.points_from_tests:
        test_ids = [UUID(v["test_id"]) for v in a.variants] if a.variants else [a.test_id]
        found = {t.id: t for t in (await session.execute(select(Test).where(Test.id.in_(test_ids)))).scalars()}
        new = []
        for tid, items in zip(test_ids, lists, strict=True):
            current = {str(i.task_id): i.points for i in found[tid].items} if tid in found else {}
            new.append([current.get(i["task_id"], i["points"]) for i in items])
    elif body.points is not None:
        if len(body.points) != len(lists) or any(len(p) != len(items) for p, items in zip(body.points, lists, strict=True)):
            raise ApiError(422, "points_shape", "Баллы нужно указать для каждого задания каждого варианта")
        new = body.points
    else:
        new = None
    if new is not None and new != [[i["points"] for i in items] for items in lists]:
        fixed = [[dict(i, points=p) for i, p in zip(items, pts, strict=True)] for items, pts in zip(lists, new, strict=True)]
        if a.variants:
            a.variants = [dict(v, items=f) for v, f in zip(a.variants, fixed, strict=True)]
            a.items = fixed[0]
        else:
            a.items = fixed[0]
        recount = True
    await session.flush()
    if recount:
        done = (await session.execute(
            select(Attempt).where(Attempt.assignment_id == a.id, Attempt.status == SUBMITTED).with_for_update()
        )).scalars().all()
        for t in done:
            await attempts.recompute(session, t, a)
    await outbox.event(
        session, "assessment.assignment.updated",
        {"assignment_id": str(a.id), "title": a.title, "teacher_id": str(a.teacher_id),
         "opens_at": a.opens_at.isoformat() if a.opens_at else None, "deadline": a.deadline.isoformat() if a.deadline else None},
        actor_id=principal.user_id,
    )
    await session.commit()
    return await assignment_out(session, a, principal, teacher_view=True)


@router.delete("/assignments/{assignment_id}", status_code=204)
async def delete_assignment(assignment_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> None:
    """Удалить назначенный тест целиком: у всех учеников, с попытками и оценками в журнале (academic — по событию)."""
    a, is_teacher = await _assignment(session, assignment_id, principal, write=True)
    if not is_teacher:
        raise ApiError(404, "assignment_not_found", "Задание не найдено")
    await _delete(session, a, principal)
    await session.commit()


async def _delete(session: AsyncSession, a: Assignment, principal: Principal) -> None:
    student_ids = [str(r.student_id) for r in a.students]
    await _drop_attempts(session, a, None)
    await session.delete(a)
    await outbox.event(
        session, "assessment.assignment.deleted",
        {"assignment_id": str(a.id), "title": a.title, "teacher_id": str(a.teacher_id), "student_ids": student_ids},
        actor_id=principal.user_id,
    )


@router.post("/assignments/{assignment_id}/remove-students", response_model=RemovedOut)
async def remove_students(
    assignment_id: UUID, body: RemoveStudentsIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> RemovedOut:
    """Убрать работу у конкретных учеников или у всех, кто её не сдал. Их попытки и оценки в журнале удаляются.
    Если учеников не осталось — назначение удаляется целиком."""
    a, is_teacher = await _assignment(session, assignment_id, principal, write=True)
    if not is_teacher:
        raise ApiError(404, "assignment_not_found", "Задание не найдено")
    targets = {r.student_id for r in a.students if r.student_id in set(body.student_ids)}
    if body.not_submitted:
        done = set((await session.execute(
            select(Attempt.student_id).where(Attempt.assignment_id == a.id, Attempt.status == SUBMITTED)
        )).scalars())
        targets |= {r.student_id for r in a.students if r.student_id not in done}
    if not targets:
        return RemovedOut(removed=0, deleted=False)
    if targets == {r.student_id for r in a.students}:
        await _delete(session, a, principal)
        await session.commit()
        return RemovedOut(removed=len(targets), deleted=True)
    await _drop_attempts(session, a, targets)
    a.students = [r for r in a.students if r.student_id not in targets]
    await outbox.event(
        session, "assessment.assignment.students_removed",
        {"assignment_id": str(a.id), "title": a.title, "teacher_id": str(a.teacher_id), "student_ids": [str(s) for s in targets]},
        actor_id=principal.user_id,
    )
    await session.commit()
    return RemovedOut(removed=len(targets), deleted=False)


@router.post("/assignments/{assignment_id}/close", response_model=AssignmentOut)
async def close(assignment_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> AssignmentOut:
    """Завершить тест на уроке: незавершённые попытки сдаются с тем, что ученики успели ответить."""
    a, is_teacher = await _assignment(session, assignment_id, principal, write=True)
    if not is_teacher:
        raise ApiError(404, "assignment_not_found", "Задание не найдено")
    a.closed_at = a.closed_at or datetime.now(UTC)
    for t in (await session.execute(select(Attempt).where(Attempt.assignment_id == a.id, Attempt.status == IN_PROGRESS))).scalars():
        await attempts.finalize(session, t, a, auto=True)
    await session.commit()
    return await assignment_out(session, a, principal, teacher_view=True)


# ---------- прохождение ----------


@router.post("/assignments/{assignment_id}/start", response_model=AttemptOut)
async def start(
    assignment_id: UUID, body: StartIn | None = None, principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> AttemptOut:
    """Начать попытку (или вернуться к начатой). Порядок заданий и вариантов — свой у каждого ученика.
    С прокторингом новая попытка начинается только с согласием ученика на мониторинг."""
    a, is_teacher = await _assignment(session, assignment_id, principal)
    if is_teacher:
        raise ApiError(403, "forbidden", "Тест проходят ученики")
    row = next(r for r in a.students if r.student_id == principal.user_id)
    mine = (await session.execute(
        select(Attempt).where(Attempt.assignment_id == a.id, Attempt.student_id == principal.user_id).with_for_update()
    )).scalars().all()
    await _sync_open(session, a, list(mine))
    current = next((t for t in mine if t.status == IN_PROGRESS), None)
    if current is None:
        now = datetime.now(UTC)
        deadline = attempts.deadline_for(a, row)
        if a.closed_at is not None:
            raise ApiError(409, "assignment_closed", "Педагог завершил тест")
        if a.opens_at and now < a.opens_at:
            raise ApiError(409, "not_open_yet", "Тест ещё не открыт")
        if deadline and now >= deadline:
            raise ApiError(409, "overdue", "Срок сдачи прошёл")
        limit = attempts.attempts_limit(a, row)
        if limit is not None and len(mine) >= limit:
            raise ApiError(409, "already_submitted", "Попытки закончились. Пройти ещё раз можно, если педагог переназначит")
        if a.proctoring and not (body and body.consent):
            raise ApiError(409, "consent_required", "Тест с прокторингом: нужно согласие на мониторинг экрана")
        settings = attempts.settings_for(a, principal.user_id)
        order = [i["task_id"] for i in attempts.items_for(a, principal.user_id)]
        rnd = random.SystemRandom()
        if settings.get("order_mode") == "random":
            rnd.shuffle(order)
        option_orders = {}
        if settings.get("shuffle_options"):
            tasks = (await session.execute(select(Task).where(Task.id.in_([UUID(i) for i in order]), Task.type == CHOICE))).scalars()
            for t in tasks:
                ids = [str(o.id) for o in t.options]
                rnd.shuffle(ids)
                option_orders[str(t.id)] = ids
        limit = settings.get("time_limit_s")
        current = Attempt(
            assignment_id=a.id, student_id=principal.user_id, number=len(mine) + 1, status=IN_PROGRESS, started_at=now,
            ends_at=now + timedelta(seconds=limit) if settings.get("time_mode") == "total" else None,
            task_order=order, option_orders=option_orders,
            current_started_at=now if settings.get("time_mode") == "per_task" else None,
            proctor_consent_at=now if a.proctoring else None,
        )
        session.add(current)
        await session.flush()
        if a.proctoring:
            session.add(ProctorEvent(attempt_id=current.id, assignment_id=a.id, student_id=principal.user_id, kind="consent", at=now))
        await outbox.event(
            session, "assessment.attempt.started",
            {"attempt_id": str(current.id), "assignment_id": str(a.id), "student_id": str(principal.user_id),
             "teacher_id": str(a.teacher_id), "watcher_ids": await class_access.watchers(a)},
            actor_id=principal.user_id,
        )
    await session.commit()
    return await attempt_out(session, current, a, principal, teacher_view=False)


async def _attempt(
    session: AsyncSession, attempt_id: UUID, p: Principal, lock: bool = False, write: bool = False
) -> tuple[Attempt, Assignment, bool]:
    t = await session.get(Attempt, attempt_id, with_for_update=lock)
    if t is not None and (a := await session.get(Assignment, t.assignment_id)).kind == SELF:
        role = await _self_viewer(session, a, t.student_id, p, write)
        if role is not None:
            return t, a, role
    elif t is not None:
        a = await session.get(Assignment, t.assignment_id)
        if a.teacher_id == p.user_id:
            return t, a, True
        if t.student_id == p.user_id:
            return t, a, False
        if await class_access.can_run(a, p):
            return t, a, True
    raise ApiError(404, "attempt_not_found", "Попытка не найдена")


async def attempt_out(session: AsyncSession, t: Attempt, a: Assignment, p: Principal, teacher_view: bool) -> AttemptOut:
    """Попытка: ученику — задания без ответов (до сдачи) и с результатами (после), педагогу — всё, с ключами."""
    submitted = t.status == SUBMITTED
    tasks = {x.id: x for x in (await session.execute(select(Task).where(Task.id.in_([UUID(i) for i in t.task_order])))).scalars()}
    drafts = {d.task_id: d for d in (await session.execute(select(AttemptAnswer).where(AttemptAnswer.attempt_id == t.id))).scalars()}
    subs = await attempts.latest_submissions(session, t.id) if submitted else {}
    urls = await _file_urls([*subs.values(), *[_Files(d.files) for d in drafts.values()]])
    points = {i["task_id"]: i["points"] for i in attempts.items_for(a, t.student_id)}
    with_file = attempts.solution_tasks(a, t.student_id)
    checks = await _checks(session, t.id)
    settings = attempts.settings_for(a, t.student_id)
    per_task = settings.get("time_mode") == "per_task"
    # «Оценка после проверки педагогом» (решение №49): до проверки ученик не видит ни итога, ни «верно/неверно», ни разбора.
    hidden = not teacher_view and a.result_after_review and t.reviewed_at is None

    out: list[AttemptTask] = []
    for n, task_id in enumerate(t.task_order):
        task = tasks.get(UUID(task_id))
        if task is None:
            continue
        # Таймер на каждое задание: следующие задания до своей очереди не показываются.
        if per_task and not submitted and not teacher_view and n > t.current_index:
            break
        # Педагог работы видит ключи всех её задач — и личных задач коллеги, чьим тестом он поделился (решение №58).
        view = await views.full(session, task, p if teacher_view else None, key=True if teacher_view else None)
        if order := t.option_orders.get(task_id):
            pos = {oid: i for i, oid in enumerate(order)}
            view.options.sort(key=lambda o: pos.get(str(o.id), 0))
        if submitted and not hidden:
            view.explanation = task.explanation  # разбор — после сдачи
        sub, draft = subs.get(task.id), drafts.get(task.id)
        answer = sub.answer if sub else (draft.answer if draft else None)
        files = sub.files if sub else (draft.files if draft else [])
        out.append(AttemptTask(
            task=view, points=points.get(task_id, 1), answer=answer,
            files=[FileRef(**f, url=urls.get(f["id"])) for f in files],
            locked=submitted or (per_task and n < t.current_index), solution_file=task_id in with_file,
            code_check=(mode := attempts.code_check(a, t.student_id, task_id)) if task.type == CODE else None,
            check=_check_out(checks.get(task.id, []), len(task.tests)) if task.type == CODE and mode == CODE_LIVE else None,
            result=views.submission_out(sub, with_log=teacher_view, urls=urls) if sub and not hidden else None,
            earned=attempts._earned(sub, points.get(task_id, 1)) if submitted and (t.checked or teacher_view) else None,
        ))
    return AttemptOut(
        id=t.id, assignment_id=a.id, self_study=a.kind == SELF, title=a.title, student_id=t.student_id, number=t.number, status=t.status,
        settings=settings, started_at=t.started_at, ends_at=t.ends_at, current_index=t.current_index,
        current_ends_at=attempts.current_ends_at(t, a) if not submitted else None, submitted_at=t.submitted_at,
        auto_submitted=t.auto_submitted, score=t.score if t.checked or teacher_view else None, max_score=t.max_score,
        percent=t.percent, grade=t.grade, checked=t.checked, needs_review=attempts.needs_review(a, t.student_id), reviewed_at=t.reviewed_at,
        grade_override=t.grade_override, grade_scale=a.grade_scale, server_time=datetime.now(UTC), proctoring=a.proctoring,
        finished_by_teacher=t.finished_by_teacher, screen_ok=_screen_ok(t, a), tasks=out, results_hidden=hidden and submitted,
    )


class _Files:
    """Обёртка, чтобы получить ссылки на файлы черновиков тем же способом, что и для отправок."""

    def __init__(self, files: list[dict]) -> None:
        self.files = files


def _screen_ok(t: Attempt, a: Assignment) -> bool:
    """Прокторинг: пока ученик не показывает экран (по данным сервера видеосвязи), ответы не принимаются."""
    return not a.proctoring or t.status != IN_PROGRESS or t.screen_sharing


def _closed(t: Attempt) -> ApiError:
    if t.finished_by_teacher:
        return ApiError(409, "finished_by_teacher", "Педагог завершил работу — ответы сохранены и отправлены")
    return ApiError(409, "time_over", "Время вышло — работа сдана автоматически")


SCREEN_REQUIRED = ApiError(409, "screen_required", "Покажите экран, чтобы продолжить — это тест с прокторингом")


async def _synced(session: AsyncSession, t: Attempt, a: Assignment) -> bool:
    """Продвинуть таймер; если время вышло — сдать. Возвращает True, если попытка ещё идёт."""
    row = next((r for r in a.students if r.student_id == t.student_id), None)
    if t.status == IN_PROGRESS and attempts.sync_timer(t, a, datetime.now(UTC), attempts.deadline_for(a, row)):
        await attempts.finalize(session, t, a, auto=True)
    return t.status == IN_PROGRESS


@router.get("/attempts/{attempt_id}", response_model=AttemptOut)
async def get_attempt(attempt_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> AttemptOut:
    t, a, is_teacher = await _attempt(session, attempt_id, principal, lock=True)
    await _synced(session, t, a)
    await session.commit()
    return await attempt_out(session, t, a, principal, teacher_view=is_teacher)


@router.put("/attempts/{attempt_id}/answers/{task_id}", response_model=AttemptOut)
async def save_answer(
    attempt_id: UUID,
    task_id: UUID,
    body: DraftIn,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> AttemptOut:
    """Сохранить черновик ответа. Проверка — только после сдачи всей работы."""
    t, a, is_teacher = await _attempt(session, attempt_id, principal, lock=True)
    if is_teacher:
        raise ApiError(403, "forbidden", "Отвечает ученик")
    if not await _synced(session, t, a):
        await session.commit()
        raise _closed(t)
    if not _screen_ok(t, a):
        raise SCREEN_REQUIRED
    if str(task_id) not in t.task_order:
        raise ApiError(404, "task_not_found", "Такого задания нет в работе")
    if attempts.settings_for(a, t.student_id).get("time_mode") == "per_task" and t.task_order.index(str(task_id)) != t.current_index:
        raise ApiError(409, "task_locked", "К этому заданию уже нельзя вернуться")
    task = await session.get(Task, task_id)
    draft = await session.get(AttemptAnswer, (t.id, task_id)) or AttemptAnswer(attempt_id=t.id, task_id=task_id, files=[])

    files = [f for f in draft.files if UUID(f["id"]) in body.file_ids]
    new_ids = [i for i in body.file_ids if str(i) not in {f["id"] for f in files}]
    files_allowed = (task.type == LONG and task.file_mode != "none") or str(task_id) in attempts.solution_tasks(a, t.student_id)
    if (new_ids or files) and not files_allowed:
        raise ApiError(422, "files_not_allowed", "К этому заданию нельзя прикрепить файл")
    if new_ids:
        claimed = await media.post(
            "/internal/files/claim",
            json={"owner_id": str(principal.user_id), "purpose": "answer", "file_ids": [str(i) for i in new_ids], "claimed_by": "assessment"},
        )
        files += [{k: f[k] for k in ("id", "filename", "mime", "size")} for f in claimed]
    draft.answer = body.answer.model_dump(exclude_none=True, mode="json")
    draft.files = files
    draft.updated_at = datetime.now(UTC)
    session.add(draft)
    await session.commit()
    return await attempt_out(session, t, a, principal, teacher_view=False)


@router.post("/attempts/{attempt_id}/tasks/{task_id}/check", response_model=AttemptOut)
async def check_code(
    attempt_id: UUID,
    task_id: UUID,
    body: CodeCheckIn,
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> AttemptOut:
    """Проверить код по кнопке (решение №49) — если так задано в тесте. Ученик видит, сколько тестов не прошло;
    проверять можно сколько угодно раз, в оценку пойдёт лучшая проверка. Код сохраняется как черновик."""
    t, a, is_teacher = await _attempt(session, attempt_id, principal, lock=True)
    if is_teacher:
        raise ApiError(403, "forbidden", "Отвечает ученик")
    if not await _synced(session, t, a):
        await session.commit()
        raise _closed(t)
    if not _screen_ok(t, a):
        raise SCREEN_REQUIRED
    if str(task_id) not in t.task_order:
        raise ApiError(404, "task_not_found", "Такого задания нет в работе")
    if attempts.code_check(a, t.student_id, str(task_id)) != CODE_LIVE:
        raise ApiError(409, "check_not_allowed", "Эту задачу проверят после сдачи работы")
    if attempts.settings_for(a, t.student_id).get("time_mode") == "per_task" and t.task_order.index(str(task_id)) != t.current_index:
        raise ApiError(409, "task_locked", "К этому заданию уже нельзя вернуться")
    if not body.code.strip():
        raise ApiError(422, "code_empty", "Напишите код")
    running = await session.scalar(
        select(func.count()).select_from(Submission).where(
            Submission.context_type == "check", Submission.context_id == t.id, Submission.task_id == task_id,
            Submission.status == CHECKING,
        )
    )
    if running:
        raise ApiError(409, "check_running", "Предыдущая проверка ещё идёт")
    now = datetime.now(UTC)
    draft = await session.get(AttemptAnswer, (t.id, task_id)) or AttemptAnswer(attempt_id=t.id, task_id=task_id, files=[])
    draft.answer, draft.updated_at = {"code": body.code}, now
    session.add(draft)
    sub = Submission(task_id=task_id, student_id=t.student_id, context_type="check", context_id=t.id,
                     answer={"code": body.code}, files=[], status=CHECKING, created_at=now)
    session.add(sub)
    await session.flush()
    await outbox.command(session, queue="assessment.code", type="assessment.code.check",
                         data={"submission_id": str(sub.id)}, actor_id=t.student_id)
    await session.commit()
    return await attempt_out(session, t, a, principal, teacher_view=False)


async def _checks(session: AsyncSession, attempt_id: UUID) -> dict[UUID, list[Submission]]:
    """Проверки по кнопке в попытке — по задачам, по порядку."""
    out: dict[UUID, list[Submission]] = {}
    for s in (await session.execute(
        select(Submission).where(Submission.context_type == "check", Submission.context_id == attempt_id).order_by(Submission.created_at)
    )).scalars():
        out.setdefault(s.task_id, []).append(s)
    return out


def _check_out(checks: list[Submission], total: int) -> CodeCheckOut | None:
    """total — тестов у задачи: песочница останавливается на первом упавшем, поэтому «не прошли» — все, кроме пройденных."""
    if not checks:
        return None
    last = checks[-1]
    done = last.status in (CORRECT, INCORRECT)
    passed = sum(1 for c in last.run_log or [] if c.get("status") == "passed")
    return CodeCheckOut(
        status=last.status, failed=(0 if last.status == CORRECT else max(1, total - passed)) if done else None,
        total=total if done else None, count=len(checks), passed_once=any(c.status == CORRECT for c in checks),
    )


@router.post("/attempts/{attempt_id}/next", response_model=AttemptOut)
async def next_task(attempt_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> AttemptOut:
    """Таймер на каждое задание: перейти к следующему (вернуться нельзя). После последнего — сдача."""
    t, a, is_teacher = await _attempt(session, attempt_id, principal, lock=True)
    if is_teacher or attempts.settings_for(a, t.student_id).get("time_mode") != "per_task":
        raise ApiError(409, "not_sequential", "В этой работе задания открыты все сразу")
    if await _synced(session, t, a):
        if not _screen_ok(t, a):
            raise SCREEN_REQUIRED
        t.current_index += 1
        t.current_started_at = datetime.now(UTC)
        if t.current_index >= len(t.task_order):
            await attempts.finalize(session, t, a, auto=False)
    await session.commit()
    return await attempt_out(session, t, a, principal, teacher_view=False)


@router.get("/attempts/{attempt_id}/status", response_model=AttemptStatusOut)
async def attempt_status(attempt_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> AttemptStatusOut:
    t, a, _ = await _attempt(session, attempt_id, principal, lock=True)
    await _synced(session, t, a)
    await session.commit()
    return AttemptStatusOut(status=t.status, screen_ok=_screen_ok(t, a), finished_by_teacher=t.finished_by_teacher)


@router.post("/attempts/{attempt_id}/finish", response_model=AttemptOut)
async def finish_by_teacher(attempt_id: UUID, principal: Principal = Depends(auth.principal),
                            session: AsyncSession = Depends(db.session)) -> AttemptOut:
    """Педагог завершает попытку ученика досрочно: сохранённые ответы отправляются на проверку, как при сдаче."""
    t, a, is_teacher = await _attempt(session, attempt_id, principal, lock=True, write=True)
    if not is_teacher:
        raise ApiError(403, "forbidden", "Завершить чужую работу может только педагог")
    if await _synced(session, t, a):
        if a.proctoring:
            session.add(ProctorEvent(attempt_id=t.id, assignment_id=a.id, student_id=t.student_id, kind="finished_by_teacher"))
        await attempts.finalize(session, t, a, auto=False, by_teacher=principal.user_id)
    await session.commit()
    return await attempt_out(session, t, a, principal, teacher_view=True)


@router.post("/attempts/{attempt_id}/submit", response_model=AttemptOut)
async def submit(attempt_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> AttemptOut:
    """Сдать работу. Отправка — один раз; повторно — только после переназначения."""
    t, a, is_teacher = await _attempt(session, attempt_id, principal, lock=True)
    if is_teacher:
        raise ApiError(403, "forbidden", "Сдаёт ученик")
    if t.status != IN_PROGRESS:
        raise ApiError(409, "already_submitted", "Работа уже сдана")
    if await _synced(session, t, a):
        await attempts.finalize(session, t, a, auto=False)
    await session.commit()
    return await attempt_out(session, t, a, principal, teacher_view=False)


@router.post("/submissions/{submission_id}/recheck", response_model=SubmissionOut)
async def recheck(submission_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> SubmissionOut:
    """Перепроверить код, если песочница была недоступна (в работе ученик не может отправить заново)."""
    sub = await session.get(Submission, submission_id, with_for_update=True)
    if sub is None or not await access.can_see_student_work(session, principal, sub.student_id):
        raise ApiError(404, "submission_not_found", "Решение не найдено")
    if sub.status != ERROR:
        raise ApiError(409, "not_failed", "Решение уже проверено")
    sub.status = CHECKING
    await outbox.command(session, queue="assessment.code", type="assessment.code.check", data={"submission_id": str(sub.id)},
                         actor_id=principal.user_id)
    await session.commit()
    return views.submission_out(sub, with_log=True)


@router.post("/attempts/{attempt_id}/review", response_model=AttemptOut)
async def review_attempt(
    attempt_id: UUID, body: AttemptReviewIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> AttemptOut:
    """Проверка работы педагогом: засчитать или не засчитать задания (в том числе проверенные автоматически)
    и поставить оценку вручную (null — по критериям работы). После этого итог виден ученику и уходит в журнал."""
    t, a, is_teacher = await _attempt(session, attempt_id, principal, lock=True, write=True)
    if not is_teacher:
        raise ApiError(404, "attempt_not_found", "Попытка не найдена")
    if t.status != SUBMITTED:
        raise ApiError(409, "not_submitted", "Ученик ещё не сдал работу")
    unknown = [str(i) for i in {*body.tasks, *body.points} if str(i) not in t.task_order]
    if unknown:
        raise ApiError(422, "task_not_found", "Такого задания нет в работе", {"task_ids": unknown})
    now = datetime.now(UTC)
    subs = await attempts.latest_submissions(session, t.id)
    item_points = {UUID(i["task_id"]): i["points"] for i in attempts.items_for(a, t.student_id)}
    # Доля балла за задание: «верно/неверно» — 1 или 0; баллы — от 0 до баллов за задание.
    shares = {task_id: 1.0 if correct else 0.0 for task_id, correct in body.tasks.items()}
    for task_id, earned in body.points.items():
        full = item_points.get(task_id, 1)
        if not 0 <= earned <= full:
            raise ApiError(422, "points_out_of_range", f"Баллы за задание — от 0 до {full}", {"task_id": str(task_id)})
        shares[task_id] = round(earned / full, 4)
    tasks = {x.id: x for x in (await session.execute(select(Task).where(Task.id.in_(list(shares))))).scalars()}
    for task_id, share in shares.items():
        sub = subs.get(task_id)
        if sub is None:
            if not share:
                continue  # без ответа и так 0 баллов
            sub = Submission(task_id=task_id, student_id=t.student_id, context_type="assignment", context_id=t.id,
                             answer={}, files=[], created_at=now)
            session.add(sub)
        # Развёрнутый ответ и частичный балл — «проверено педагогом» с долей балла; иначе — верно/неверно.
        partial = 0 < share < 1
        sub.status = REVIEWED if tasks[task_id].type == LONG or partial else CORRECT if share else INCORRECT
        sub.score, sub.checked_at = share, sub.checked_at or now
        sub.reviewer_id, sub.reviewed_at = principal.user_id, now
    t.reviewed_at, t.grade_override = now, body.grade
    await session.flush()
    await attempts.recompute(session, t, a)
    await outbox.event(
        session, "assessment.attempt.reviewed",
        {"attempt_id": str(t.id), "assignment_id": str(a.id), "student_id": str(t.student_id), "teacher_id": str(a.teacher_id),
         "tasks": {str(k): v for k, v in body.tasks.items()}, "points": {str(k): v for k, v in body.points.items()},
         "grade": t.grade, "grade_override": body.grade, "watcher_ids": await class_access.watchers(a)},
        actor_id=principal.user_id,
    )
    await session.commit()
    return await attempt_out(session, t, a, principal, teacher_view=True)


# ---------- прокторинг ----------

MAX_PROCTOR_EVENTS = 1000  # на попытку — защита от засорения журнала


@router.post("/attempts/{attempt_id}/proctor-events", status_code=204)
async def proctor_event(
    attempt_id: UUID, body: ProctorEventIn, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> None:
    """Страница теста сообщает о событиях: показ экрана, смена вкладки, камера. Педагог видит их сразу — через комнату
    прокторинга, а здесь они сохраняются для разбора после теста."""
    t, a, is_teacher = await _attempt(session, attempt_id, principal)
    if is_teacher or not a.proctoring:
        raise ApiError(404, "attempt_not_found", "Попытка не найдена")
    if t.status != IN_PROGRESS:
        return
    count = await session.scalar(select(func.count()).select_from(ProctorEvent).where(ProctorEvent.attempt_id == t.id))
    if count >= MAX_PROCTOR_EVENTS:
        return
    session.add(ProctorEvent(attempt_id=t.id, assignment_id=a.id, student_id=t.student_id, kind=body.kind))
    await session.commit()


@router.get("/attempts/{attempt_id}/proctor-events", response_model=list[ProctorEventOut])
async def proctor_events(attempt_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> list[ProctorEventOut]:
    t, _, _ = await _attempt(session, attempt_id, principal)
    rows = (await session.execute(select(ProctorEvent).where(ProctorEvent.attempt_id == t.id).order_by(ProctorEvent.at))).scalars()
    return [ProctorEventOut(kind=e.kind, at=e.at) for e in rows]
