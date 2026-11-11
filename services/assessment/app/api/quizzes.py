"""Тесты педагога: набор задач из банка с настройками (порядок, перемешивание, таймер)."""

from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_MODERATOR, ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import access, sharing, views
from ..courses import course_test_for, in_review, module_info, modules_info, visibility, write_test
from ..deps import auth, db, outbox
from ..handlers import _publish as publish_task
from ..models import CODE, CODE_AFTER, CODE_MANUAL, SOLUTION_FILE_TYPES, Assignment, Task, Test, TestItem, TestShare
from ..schemas import ModuleRef, QuizIn, QuizItemOut, QuizOut, QuizSummary, TestShareIn, TestShareOut

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


async def _assignments_count(session: AsyncSession, ids, teacher_id: UUID | None = None) -> dict[UUID, int]:
    """Сколько раз тест назначали: сам или вариантом в чужой работе (решение №48)."""
    ids = list(ids)
    if not ids:
        return {}
    plain = select(Assignment.test_id, func.count()).where(Assignment.test_id.in_(ids), Assignment.variants.is_(None))
    variant = func.jsonb_array_elements(Assignment.variants).table_valued("value").lateral("v")
    variant_test = variant.c.value.op("->>")("test_id")
    in_variants = (
        select(variant_test, func.count()).select_from(Assignment).join(variant, true())
        .where(func.jsonb_typeof(Assignment.variants) == "array", variant_test.in_([str(i) for i in ids]))
    )
    if teacher_id is not None:
        plain = plain.where(Assignment.teacher_id == teacher_id)
        in_variants = in_variants.where(Assignment.teacher_id == teacher_id)
    counts = dict((await session.execute(plain.group_by(Assignment.test_id))).all())
    for test_id, n in (await session.execute(in_variants.group_by(variant_test))).all():
        counts[UUID(test_id)] = counts.get(UUID(test_id), 0) + n
    return counts


def pending_view(test: Test) -> Test:
    """Тест с предложенными изменениями (не в базе) — так автор видит и правит то, что уйдёт на проверку."""
    body = QuizIn.model_validate(test.pending)
    view = Test(id=test.id, owner_id=test.owner_id, shared=test.shared, published_at=test.published_at, updated_at=test.updated_at)
    write_test(view, body, test.pending.get("module"))
    return view


async def quiz_out(session: AsyncSession, test: Test, viewer: Principal | None = None, shared: bool = False,
                   review: bool = False) -> QuizOut:
    """viewer — чужой педагог (тест автора курса, решение №46, или коллега, с которым поделились, — shared, №58):
    принятая версия только для просмотра, назначения — его собственные. review — модератор проверяет тест вместе
    с курсом: видит предложенную версию, тоже только для просмотра."""
    await session.refresh(test)
    view = pending_view(test) if test.pending and (viewer is None or review) else test
    tasks = {t.id: t for t in (await session.execute(select(Task).where(Task.id.in_([i.task_id for i in view.items])))).scalars()}
    summaries = {s.id: s for s in await views.summaries(session, list(tasks.values()))}
    module = (await modules_info([view.module_id], test.owner_id)).get(view.module_id) if view.module_id else None
    return QuizOut(
        id=test.id, title=view.title, description=view.description, grade_level=view.grade_level,
        subject_id=view.subject_id, subject_name=view.subject_name, order_mode=view.order_mode,
        shuffle_options=view.shuffle_options, time_mode=view.time_mode, time_limit_s=view.time_limit_s,
        theme=view.theme, module=module_ref(view), shared=view.shared, visibility=visibility(test.owner_id, view.shared, module),
        published=test.published_at is not None, pending=test.pending is not None,
        items=[QuizItemOut(task_id=i.task_id, points=i.points, solution_file=i.solution_file, code_check=i.code_check,
                               task=summaries[i.task_id])
               for i in view.items if i.task_id in summaries],
        max_score=sum(i.points for i in view.items),
        assignments_count=(await _assignments_count(session, [test.id], viewer.user_id if viewer else None)).get(test.id, 0),
        updated_at=test.updated_at, can_edit=viewer is None, shared_with_me=shared, can_share=viewer is None or shared,
        owner_name=(await views.names(session, [test.owner_id])).get(test.owner_id, "Автор") if viewer else None,
        review=None if not review else "new" if test.published_at is None else "changed" if test.pending else None,
    )


@router.get("", response_model=list[QuizSummary])
async def my_tests(
    module_id: UUID | None = Query(None, description="Только тесты, привязанные к модулю курса"),
    grade_level: str | None = Query(None, pattern=r"^(none|\d{1,2})$", description="Класс; none — класс не указан"),
    offset: int = Query(0, ge=0),
    limit: int | None = Query(None, ge=1, le=200, description="Постранично; без limit — все (для выбора теста в формах)"),
    principal: Principal = Depends(author),
    session: AsyncSession = Depends(db.session),
) -> list[QuizSummary]:
    # Свои тесты и тесты, которыми поделились коллеги (решение №58); тесты модуля — только свои.
    if module_id:
        query = select(Test).where(Test.owner_id == principal.user_id, Test.module_id == module_id)
    else:
        query = select(Test).where(or_(Test.owner_id == principal.user_id, Test.id.in_(sharing.shared_ids(principal.user_id))))
    if grade_level:
        query = query.where(Test.grade_level.is_(None) if grade_level == "none" else Test.grade_level == int(grade_level))
    query = query.order_by(Test.updated_at.desc(), Test.id.desc()).offset(offset)
    if limit:
        query = query.limit(limit)
    tests = (await session.execute(query)).scalars().all()
    counts = await _assignments_count(session, [t.id for t in tests if t.owner_id == principal.user_id])
    others = [t.id for t in tests if t.owner_id != principal.user_id]
    counts |= await _assignments_count(session, others, principal.user_id)  # у чужого теста — только свои назначения
    authors = await views.names(session, {t.owner_id for t in tests if t.owner_id != principal.user_id})
    modules = await modules_info([t.module_id for t in tests], principal.user_id)
    return [
        QuizSummary(id=t.id, title=t.title, grade_level=t.grade_level, subject_name=t.subject_name, module=module_ref(t), shared=t.shared,
                    visibility=visibility(t.owner_id, t.shared, modules.get(t.module_id)), published=t.published_at is not None,
                    pending=t.pending is not None, tasks_count=len(t.items), max_score=sum(i.points for i in t.items),
                    time_mode=t.time_mode, time_limit_s=t.time_limit_s, assignments_count=counts.get(t.id, 0), updated_at=t.updated_at,
                    shared_with_me=t.owner_id != principal.user_id, owner_name=authors.get(t.owner_id))
        for t in tests
    ]


IN_REVIEW = "Курс на проверке у модератора — тесты автора к нему меняются после решения"


async def _validate(session: AsyncSession, test: Test, body: QuizIn, p: Principal) -> dict | None:
    """Задачи доступны, модуль можно привязать, «публичный» — только у автора курса. Возвращает сведения о модуле."""
    # В тест можно добавить свою задачу (в любом статусе) или опубликованную из банка.
    tasks = {t.id: t for t in (await session.execute(select(Task).where(Task.id.in_([i.task_id for i in body.items])))).scalars()}
    if body.subject_id is None:  # предмет не выбран — самый частый у задач теста (решение №59)
        found = Counter((t.subject_id, t.subject_name) for t in tasks.values() if t.subject_id)
        if found:
            body.subject_id, body.subject_name = found.most_common(1)[0][0]
    if body.subject_id is None or not body.subject_name:
        raise ApiError(422, "subject_required", "Выберите предмет теста — по нему оценки попадают в журнал")
    for item in body.items:
        task = tasks.get(item.task_id)
        if task is None or not await access.can_view(session, task, p) or not (task.owner_id == p.user_id or task.status == "published") \
                or task.status == "removed":
            raise ApiError(422, "task_not_available", "Задача недоступна — возможно, её сняли с публикации")
        if item.solution_file and task.type not in SOLUTION_FILE_TYPES:
            raise ApiError(422, "solution_file_not_allowed", "Файл с решением можно запросить только к короткому ответу и выбору варианта")
        if task.type != CODE:
            item.code_check = CODE_AFTER  # способ проверки — только у кода
        elif item.code_check != CODE_MANUAL and not task.tests:
            raise ApiError(422, "code_tests_required", f"У задачи «{task.title}» нет тестов — выберите проверку педагогом")
    module = await module_info(body.module_id, p.user_id) if body.module_id else None
    # Курс сняли с публикации — прежняя привязка остаётся, новую не сделать.
    if body.module_id and not (module and module["usable"]) and body.module_id != test.module_id:
        raise ApiError(422, "module_not_available", "Модуль не найден — привязать тест можно к своему или опубликованному курсу")
    if body.shared and (module is None or UUID(module["owner_id"]) != p.user_id):
        raise ApiError(422, "shared_not_author", "Публичным может быть только тест автора курса")
    return module


async def _apply(session: AsyncSession, test: Test, body: QuizIn, p: Principal) -> None:
    """Сохранить тест (решение №46). Тест автора курса виден другим, только когда принят вместе с курсом:
    правка принятого теста опубликованного курса — предложение, которое модератор проверит с черновиком курса;
    курсы штатных редакторов (модератор, администратор) публикуются сразу — и их тесты тоже."""
    module = await _validate(session, test, body, p)
    author_test = module is not None and UUID(module["owner_id"]) == p.user_id
    current = None
    if test.published_at and test.module_id:  # тест уже виден другим — правила его курса
        current = module if body.module_id == test.module_id else await module_info(test.module_id, p.user_id)
    if p.has_any(ROLE_MODERATOR):
        test.pending = None
        write_test(test, body, module)
        if author_test and module["course_status"] == "published":
            await _publish_now(session, test, p)
        return
    for m in (current, module if author_test else None):
        if m is not None and UUID(m["owner_id"]) == p.user_id and in_review(m):
            raise ApiError(409, "course_in_review", IN_REVIEW)
    if current is not None and UUID(current["owner_id"]) == test.owner_id and current["course_status"] == "published":
        mod = {k: module[k] for k in ("course_id", "title", "course_title")} if module else None
        test.pending = body.model_dump(mode="json") | {"module": mod}
        test.updated_at = datetime.now(UTC)
        return
    write_test(test, body, module)


async def _publish_now(session: AsyncSession, test: Test, p: Principal) -> None:
    """Тест штатного редактора к опубликованному курсу: виден сразу, его личные задачи — сразу публичные."""
    test.published_at = test.published_at or datetime.now(UTC)
    tasks = (await session.execute(select(Task).where(Task.id.in_([i.task_id for i in test.items]), Task.owner_id == p.user_id,
                                                      Task.status.in_(("private", "rejected", "pending"))))).scalars()
    for task in tasks:
        await publish_task(session, task, True, None, p.user_id)


@router.post("", response_model=QuizOut, status_code=201)
async def create(body: QuizIn, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> QuizOut:
    test = Test(owner_id=principal.user_id)
    await _apply(session, test, body, principal)
    session.add(test)
    await session.commit()
    return await quiz_out(session, test)


@router.get("/{test_id}", response_model=QuizOut)
async def get(test_id: UUID, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> QuizOut:
    """Свой тест — для правки; тест автора курса, который виден педагогу, — только для просмотра (решение №46)."""
    test = await session.get(Test, test_id)
    if test is not None and test.owner_id == principal.user_id:
        return await quiz_out(session, test)
    if await sharing.share_of(session, test, principal) is not None:
        return await quiz_out(session, test, viewer=principal, shared=True)
    if await course_test_for(session, test, principal) is not None:
        return await quiz_out(session, test, viewer=principal)
    # Модератор проверяет тесты автора курса вместе с курсом или черновиком — в том числе ещё не принятые (№46).
    if test is not None and test.module_id and principal.has_any(ROLE_MODERATOR):
        module = await module_info(test.module_id, principal.user_id)
        if module is not None and UUID(module["owner_id"]) == test.owner_id:
            return await quiz_out(session, test, viewer=principal, review=True)
    raise ApiError(404, "test_not_found", "Тест не найден")


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
    if test.published_at and test.module_id and not principal.has_any(ROLE_MODERATOR):
        module = await module_info(test.module_id, principal.user_id)
        if module and UUID(module["owner_id"]) == test.owner_id and module["course_status"] in ("published", "pending"):
            raise ApiError(409, "course_test_published", "Тест — часть опубликованного курса: уберите его из курса через черновик "
                                                          "изменений (отвяжите от модуля) и отправьте на проверку")
    if (await _assignments_count(session, [test.id])).get(test.id):
        raise ApiError(409, "test_assigned", "Тест уже выдавали — его результаты хранятся, удалить нельзя")
    await session.delete(test)
    await session.commit()


# ---------- общий доступ коллегам (решение №58) ----------


async def _shareable(session: AsyncSession, test_id: UUID, p: Principal) -> Test:
    test = await session.get(Test, test_id)
    if test is None or not await sharing.can_share(session, test, p):
        raise ApiError(404, "test_not_found", "Тест не найден")
    return test


async def _shares_out(session: AsyncSession, test: Test, p: Principal) -> list[TestShareOut]:
    rows = (await session.execute(select(TestShare).where(TestShare.test_id == test.id).order_by(TestShare.created_at))).scalars().all()
    names = await views.names(session, {r.user_id for r in rows} | {r.shared_by for r in rows})
    return [TestShareOut(user_id=r.user_id, full_name=names.get(r.user_id, "Педагог"), shared_by=r.shared_by,
                         shared_by_name=names.get(r.shared_by, "Педагог"),
                         created_at=r.created_at, can_remove=p.user_id in (test.owner_id, r.shared_by))
            for r in rows]


@router.get("/{test_id}/shares", response_model=list[TestShareOut])
async def shares(test_id: UUID, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> list[TestShareOut]:
    """С кем из коллег поделились тестом."""
    return await _shares_out(session, await _shareable(session, test_id, principal), principal)


@router.post("/{test_id}/shares", response_model=list[TestShareOut], status_code=201)
async def share(
    test_id: UUID, body: TestShareIn, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)
) -> list[TestShareOut]:
    """Поделиться тестом с коллегой: автор или тот, с кем им уже поделились. Личные задачи теста остаются личными."""
    test = await _shareable(session, test_id, principal)
    if body.colleague_id in (principal.user_id, test.owner_id):
        raise ApiError(422, "share_self", "Это автор теста — у него тест и так есть")
    if not await sharing.are_colleagues(principal.user_id, body.colleague_id):
        raise ApiError(422, "not_colleague", "Поделиться можно только с коллегой — добавьте его в разделе «Мои коллеги»")
    if await session.get(TestShare, (test.id, body.colleague_id)) is None:
        session.add(TestShare(test_id=test.id, user_id=body.colleague_id, shared_by=principal.user_id))
        await session.flush()
        await outbox.event(
            session, "assessment.test.shared",
            {"test_id": str(test.id), "title": test.title, "owner_id": str(test.owner_id), "to_id": str(body.colleague_id),
             "actor_name": (await views.names(session, [principal.user_id])).get(principal.user_id, "Коллега")},
            actor_id=principal.user_id,
        )
    await session.commit()
    return await _shares_out(session, test, principal)


@router.delete("/{test_id}/shares/{user_id}", status_code=204)
async def unshare(test_id: UUID, user_id: UUID, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> None:
    """Закрыть доступ: автор — любому, поделившийся — тем, с кем поделился сам, коллега — себе («убрать из моих тестов»).
    Его назначения по тесту остаются."""
    test = await session.get(Test, test_id)
    row = await session.get(TestShare, (test_id, user_id)) if test is not None else None
    if row is None or principal.user_id not in (test.owner_id, row.shared_by, row.user_id):
        raise ApiError(404, "share_not_found", "Доступа к тесту нет")
    await session.delete(row)
    await session.commit()
