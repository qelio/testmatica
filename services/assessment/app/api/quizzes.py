"""Тесты педагога: набор задач из банка с настройками (порядок, перемешивание, таймер)."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_MODERATOR, ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import access, views
from ..courses import course_editable, module_info
from ..deps import auth, db
from ..models import SOLUTION_FILE_TYPES, Assignment, Task, Test, TestItem
from ..schemas import ModuleRef, QuizIn, QuizItemOut, QuizOut, QuizSummary

router = APIRouter(prefix="/tests", tags=["tests"])
author = auth.require(ROLE_TEACHER, ROLE_MODERATOR)


async def own_test(session: AsyncSession, test_id: UUID, p: Principal, lock: bool = False) -> Test:
    test = await session.get(Test, test_id, with_for_update=lock)
    if test is None or test.owner_id != p.user_id:
        raise ApiError(404, "test_not_found", "Тест не найден")
    return test


def module_ref(test: Test) -> ModuleRef | None:
    if test.module_id is None:
        return None
    return ModuleRef(id=test.module_id, title=test.module_title or "", course_id=test.course_id, course_title=test.course_title)


async def _assignments_count(session: AsyncSession, ids) -> dict[UUID, int]:
    ids = list(ids)
    if not ids:
        return {}
    rows = await session.execute(select(Assignment.test_id, func.count()).where(Assignment.test_id.in_(ids)).group_by(Assignment.test_id))
    return dict(rows.all())


async def quiz_out(session: AsyncSession, test: Test) -> QuizOut:
    await session.refresh(test)
    tasks = {t.id: t for t in (await session.execute(select(Task).where(Task.id.in_([i.task_id for i in test.items])))).scalars()}
    summaries = {s.id: s for s in await views.summaries(session, list(tasks.values()))}
    return QuizOut(
        id=test.id, title=test.title, description=test.description, grade_level=test.grade_level, order_mode=test.order_mode,
        shuffle_options=test.shuffle_options, time_mode=test.time_mode, time_limit_s=test.time_limit_s,
        theme=test.theme, module=module_ref(test), shared=test.shared, items=[QuizItemOut(task_id=i.task_id, points=i.points, solution_file=i.solution_file, task=summaries[i.task_id]) for i in test.items if i.task_id in summaries],
        max_score=sum(i.points for i in test.items),
        assignments_count=(await _assignments_count(session, [test.id])).get(test.id, 0),
        updated_at=test.updated_at,
    )


@router.get("", response_model=list[QuizSummary])
async def my_tests(
    module_id: UUID | None = Query(None, description="Только тесты, привязанные к модулю курса"),
    principal: Principal = Depends(author),
    session: AsyncSession = Depends(db.session),
) -> list[QuizSummary]:
    query = select(Test).where(Test.owner_id == principal.user_id)
    if module_id:
        query = query.where(Test.module_id == module_id)
    tests = (await session.execute(query.order_by(Test.updated_at.desc()))).scalars().all()
    counts = await _assignments_count(session, [t.id for t in tests])
    return [
        QuizSummary(id=t.id, title=t.title, grade_level=t.grade_level, module=module_ref(t), shared=t.shared, tasks_count=len(t.items), max_score=sum(i.points for i in t.items),
                    time_mode=t.time_mode, time_limit_s=t.time_limit_s, assignments_count=counts.get(t.id, 0), updated_at=t.updated_at)
        for t in tests
    ]


COURSE_LOCKED = "Публичный тест — часть курса, а курс на модерации или опубликован. Измените его, сняв курс с публикации"


async def _check_course_editable(test: Test, p: Principal, module: dict | None = None) -> None:
    """Общий тест меняется и удаляется, только пока его курс можно править (курс удалили — можно всегда)."""
    module = module or await module_info(test.module_id, p.user_id)
    if module is not None and not course_editable(module, p):
        raise ApiError(409, "course_locked", COURSE_LOCKED)


async def _apply(session: AsyncSession, test: Test, body: QuizIn, p: Principal) -> None:
    # В тест можно добавить свою задачу (в любом статусе) или опубликованную из банка.
    tasks = {t.id: t for t in (await session.execute(select(Task).where(Task.id.in_([i.task_id for i in body.items])))).scalars()}
    for item in body.items:
        task = tasks.get(item.task_id)
        if task is None or not await access.can_view(session, task, p) or not (task.owner_id == p.user_id or task.status == "published") \
                or task.status == "removed":
            raise ApiError(422, "task_not_available", "Задача недоступна — возможно, её сняли с публикации")
        if item.solution_file and task.type not in SOLUTION_FILE_TYPES:
            raise ApiError(422, "solution_file_not_allowed", "Файл с решением можно запросить только к короткому ответу и выбору варианта")
    module = await module_info(body.module_id, p.user_id) if body.module_id else None
    if test.shared:
        await _check_course_editable(test, p, module if body.module_id == test.module_id else None)
    if body.module_id is None:
        test.module_id = test.course_id = test.module_title = test.course_title = None
    else:
        # Названия обновляются при каждом сохранении. Курс сняли с публикации — прежняя привязка остаётся, новую не сделать.
        if module is not None and module["usable"]:
            test.module_id, test.course_id = body.module_id, UUID(module["course_id"])
            test.module_title, test.course_title = module["title"], module["course_title"]
        elif body.module_id != test.module_id:
            raise ApiError(422, "module_not_available", "Модуль не найден — привязать тест можно к своему или опубликованному курсу")
    if body.shared:
        # «Для всех» — часть курса: только у автора курса и публикуется вместе с ним (через модерацию).
        if module is None or UUID(module["owner_id"]) != p.user_id:
            raise ApiError(422, "shared_not_author", "Публичным может быть только тест автора курса")
        if not course_editable(module, p):
            raise ApiError(409, "course_locked", COURSE_LOCKED)
    test.shared = body.shared
    # Оформление — как у курса привязанного модуля, у остальных тестов — обычное (решение №44).
    test.theme = "course" if test.module_id else "classic"
    for field in ("title", "description", "grade_level", "order_mode", "shuffle_options", "time_mode", "time_limit_s"):
        setattr(test, field, getattr(body, field))
    test.items = [TestItem(task_id=i.task_id, points=i.points, solution_file=i.solution_file, position=n) for n, i in enumerate(body.items)]
    test.updated_at = datetime.now(UTC)


@router.post("", response_model=QuizOut, status_code=201)
async def create(body: QuizIn, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> QuizOut:
    test = Test(owner_id=principal.user_id)
    await _apply(session, test, body, principal)
    session.add(test)
    await session.commit()
    return await quiz_out(session, test)


@router.get("/{test_id}", response_model=QuizOut)
async def get(test_id: UUID, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> QuizOut:
    return await quiz_out(session, await own_test(session, test_id, principal))


@router.put("/{test_id}", response_model=QuizOut)
async def update(
    test_id: UUID, body: QuizIn, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)
) -> QuizOut:
    """Правка не затрагивает уже выданные ДЗ: у них своя копия состава и настроек."""
    test = await own_test(session, test_id, principal, lock=True)
    await _apply(session, test, body, principal)
    await session.commit()
    return await quiz_out(session, test)


@router.delete("/{test_id}", status_code=204)
async def delete(test_id: UUID, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> None:
    test = await own_test(session, test_id, principal, lock=True)
    if test.shared:
        await _check_course_editable(test, principal)
    if (await _assignments_count(session, [test.id])).get(test.id):
        raise ApiError(409, "test_assigned", "Тест уже выдавали — его результаты хранятся, удалить нельзя")
    await session.delete(test)
    await session.commit()
