"""Общие тесты курса (решение №44): тесты автора курса «для всех» под модулем, самостоятельное прохождение
и работы ученика «для себя» — для его педагогов."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import access, views
from ..courses import course_readable, course_test_for, is_teacher, module_info
from ..deps import auth, db
from ..models import SELF, Assignment, AssignmentStudent, Test
from ..schemas import AssignmentOut, AttemptOut, CourseTestOut, QuizSummary
from .assignments import assignment_out, copy_of, start, test_theme
from .quizzes import _assignments_count, module_ref

router = APIRouter(tags=["course-tests"])


async def _readable_module(session: AsyncSession, module_id: UUID, user_id: UUID | None) -> dict | None:
    module = await module_info(module_id, user_id)
    return module if module is not None and await course_readable(session, module, user_id) else None


async def _latest_self(session: AsyncSession, test: Test, student_id: UUID) -> Assignment | None:
    return await session.scalar(
        select(Assignment).where(Assignment.kind == SELF, Assignment.test_id == test.id, Assignment.target_id == student_id)
        .order_by(Assignment.created_at.desc()).limit(1)
    )


@router.get("/course-tests", response_model=list[CourseTestOut])
async def course_tests(
    module_id: UUID = Query(description="Модуль курса"),
    principal: Principal | None = Depends(auth.optional),
    session: AsyncSession = Depends(db.session),
) -> list[CourseTestOut]:
    """Тесты автора курса под модулем (решение №46), принятые вместе с курсом: публичные — всем, кто видит курс
    (ученику — с его самостоятельной работой), «для педагогов» — ещё и педагогам."""
    user_id = principal.user_id if principal else None
    module = await _readable_module(session, module_id, user_id)
    if module is None:
        return []
    query = select(Test).where(Test.module_id == module_id, Test.owner_id == UUID(module["owner_id"]), Test.published_at.is_not(None))
    if not is_teacher(principal):
        query = query.where(Test.shared.is_(True))
    tests = (await session.execute(query.order_by(Test.shared.desc(), Test.created_at))).scalars().all()
    out = []
    for t in tests:
        own = await _latest_self(session, t, user_id) if user_id else None
        out.append(CourseTestOut(
            id=t.id, title=t.title, description=t.description, owner_id=t.owner_id, tasks_count=len(t.items),
            max_score=sum(i.points for i in t.items), time_mode=t.time_mode, time_limit_s=t.time_limit_s,
            visibility="public" if t.shared else "teachers",
            self_assignment=await assignment_out(session, own, principal, teacher_view=False) if own else None,
        ))
    await session.commit()  # просроченные попытки могли сдаться при просмотре
    return out


@router.get("/course-tests/{test_id}", response_model=QuizSummary)
async def course_test(
    test_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> QuizSummary:
    """Тест автора курса (публичный или «для педагогов») — для формы назначения: его назначает любой педагог,
    которому виден курс."""
    test = await session.get(Test, test_id)
    if not is_teacher(principal) or await course_test_for(session, test, principal) is None:
        raise ApiError(404, "test_not_found", "Тест не найден")
    mine = (await _assignments_count(session, [test.id], principal.user_id)).get(test.id, 0)
    return QuizSummary(
        id=test.id, title=test.title, grade_level=test.grade_level, module=module_ref(test), shared=test.shared,
        visibility="public" if test.shared else "teachers", published=True,
        tasks_count=len(test.items), max_score=sum(i.points for i in test.items), time_mode=test.time_mode,
        time_limit_s=test.time_limit_s, assignments_count=mine or 0, updated_at=test.updated_at,
    )


@router.post("/course-tests/{test_id}/start", response_model=AttemptOut)
async def start_self(
    test_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> AttemptOut:
    """Пройти общий тест самому: без срока и журнала, попыток сколько угодно. Тест изменился — новая работа
    с новым составом, прежние попытки остаются в старой."""
    test = await session.get(Test, test_id)
    # Сам проходят только публичные (принятые с курсом) тесты автора курса.
    if test is None or not test.shared or await course_test_for(session, test, principal) is None:
        raise ApiError(404, "test_not_found", "Тест не найден")
    if not test.items:
        raise ApiError(422, "test_empty", "В тесте пока нет заданий")
    a = await _latest_self(session, test, principal.user_id)
    if a is None or a.created_at < test.updated_at:
        name = (await views.names(session, [principal.user_id])).get(principal.user_id, "Ученик")
        a = Assignment(
            **copy_of(test, await test_theme(test, principal.user_id)), teacher_id=principal.user_id, title=test.title,
            kind=SELF, target_type="student", target_id=principal.user_id, target_title=name,
            max_attempts=None, grade_to_journal=False,
            students=[AssignmentStudent(student_id=principal.user_id, allowed_attempts=1)],
        )
        session.add(a)
        await session.commit()
    return await start(a.id, None, principal, session)


@router.get("/students/{student_id}/self-work", response_model=list[AssignmentOut])
async def self_work(
    student_id: UUID, principal: Principal = Depends(auth.require(ROLE_TEACHER)), session: AsyncSession = Depends(db.session)
) -> list[AssignmentOut]:
    """Педагогу — что его ученик проходил по курсам сам."""
    if not await access.linked(session, principal.user_id, student_id):
        raise ApiError(404, "student_not_found", "Ученик не привязан к вам")
    found = (await session.execute(
        select(Assignment).where(Assignment.kind == SELF, Assignment.target_id == student_id)
        .order_by(Assignment.created_at.desc()).limit(100)
    )).scalars().all()
    out = [await assignment_out(session, a, principal, teacher_view=True) for a in found]
    await session.commit()
    return out

