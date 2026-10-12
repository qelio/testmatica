"""Курсы библиотеки (content) глазами assessment: модули, к которым привязаны тесты (решения №43, 44).

Сведения о модуле берутся из content (`/internal/modules/lookup`); права повторяют правила библиотеки:
читать курс — опубликованный всем, черновик — автору и привязанным к нему ученикам; менять — автору,
пока курс в черновике или отклонён (опубликованный — только штатному редактору)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_MODERATOR, ROLE_TEACHER, Principal

from . import access
from .deps import content
from .models import Test, TestItem
from .schemas import QuizIn

PUBLISHED, REMOVED = "published", "removed"


async def module_info(module_id: UUID, user_id: UUID | None) -> dict | None:
    """Модуль: названия, курс, его тема, статус и автор; usable — можно ли этому пользователю привязать к нему тест."""
    found = await content.post(
        "/internal/modules/lookup",
        json={"module_ids": [str(module_id)], "user_id": str(user_id or UUID(int=0))},
    )
    return found[0] if found else None


async def modules_info(module_ids, user_id: UUID | None) -> dict[UUID, dict]:
    """То же для нескольких модулей сразу: id модуля → сведения (нет модуля — нет и ключа)."""
    ids = list({str(m) for m in module_ids if m})
    if not ids:
        return {}
    found = await content.post("/internal/modules/lookup", json={"module_ids": ids, "user_id": str(user_id or UUID(int=0))})
    return {UUID(m["id"]): m for m in found}


def is_teacher(p: Principal | None) -> bool:
    return p is not None and p.has_any(ROLE_TEACHER, ROLE_MODERATOR)


async def course_test_for(session: AsyncSession, test, p: Principal | None) -> dict | None:
    """Тест автора курса, который этот пользователь видит (решение №46): принят вместе с курсом, курс ему виден;
    публичный — всем, «для педагогов» — педагогам. Возвращает сведения о модуле или None."""
    if test is None or test.module_id is None or test.published_at is None:
        return None
    module = await module_info(test.module_id, p.user_id if p else None)
    if module is None or UUID(module["owner_id"]) != test.owner_id:
        return None
    if not (test.shared or is_teacher(p)):
        return None
    return module if await course_readable(session, module, p.user_id if p else None) else None


async def course_task_visible(session: AsyncSession, task, p: Principal | None) -> bool:
    """Задача из теста автора курса, который виден этому педагогу (решение №46): её можно смотреть вместе с тестом,
    даже пока она личная у автора — с условием и ответами, как у опубликованной."""
    if not is_teacher(p):
        return False
    tests = (await session.execute(
        select(Test).join(TestItem, TestItem.test_id == Test.id)
        .where(TestItem.task_id == task.id, Test.owner_id == task.owner_id, Test.published_at.is_not(None))
    )).scalars().unique().all()
    for t in tests:
        if await course_test_for(session, t, p) is not None:
            return True
    return False


def in_review(module: dict) -> bool:
    """Курс (или его черновик изменений) на проверке у модератора — тесты автора к нему не меняются."""
    return module["course_status"] == "pending" or module.get("revision_status") == "pending"


def visibility(owner_id: UUID, shared: bool, module: dict | None) -> str | None:
    """Вид теста при модуле (решение №46): автора курса — public (ученикам и педагогам) или teachers (всем педагогам),
    любого другого педагога — private (только ему). Без модуля — None."""
    if module is None:
        return None
    if UUID(module["owner_id"]) == owner_id:
        return "public" if shared else "teachers"
    return "private"


def course_editable(module: dict, p: Principal) -> bool:
    if UUID(module["owner_id"]) != p.user_id:
        return False
    status = module["course_status"]
    return status in ("private", "rejected") or (status == PUBLISHED and p.has_any(ROLE_MODERATOR))


async def course_readable(session: AsyncSession, module: dict, user_id: UUID | None) -> bool:
    status, owner = module["course_status"], UUID(module["owner_id"])
    if status == PUBLISHED:
        return True
    if user_id is None:
        return False
    if owner == user_id:
        return True
    return status != REMOVED and await access.linked(session, owner, user_id)


def write_test(test: Test, body: QuizIn, module: dict | None) -> None:
    """Перенести тело запроса в тест. module — сведения о модуле ({course_id, title, course_title}) или None."""
    if body.module_id is None:
        test.module_id = test.course_id = test.module_title = test.course_title = None
    elif module is not None:  # названия обновляются при каждом сохранении
        test.module_id, test.course_id = body.module_id, UUID(str(module["course_id"]))
        test.module_title, test.course_title = module["title"], module["course_title"]
    test.shared = body.shared
    # Оформление — как у курса привязанного модуля, у остальных тестов — обычное (решение №44).
    test.theme = "course" if test.module_id else "classic"
    for field in ("title", "description", "grade_level", "order_mode", "shuffle_options", "time_mode", "time_limit_s"):
        setattr(test, field, getattr(body, field))
    test.items = [TestItem(task_id=i.task_id, points=i.points, solution_file=i.solution_file, position=n) for n, i in enumerate(body.items)]
    test.updated_at = datetime.now(UTC)


def test_task_ids(test: Test) -> list[UUID]:
    """Задачи теста — с учётом предложенных изменений (их проверяют вместе с курсом)."""
    if test.pending:
        return [UUID(str(i["task_id"])) for i in test.pending.get("items", [])]
    return [i.task_id for i in test.items]


def apply_pending(test: Test) -> None:
    """Принятые модератором изменения теста — в сам тест."""
    if test.pending:
        write_test(test, QuizIn.model_validate(test.pending), test.pending.get("module"))
        test.pending = None
