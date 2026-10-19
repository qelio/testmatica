"""Тесты, которыми поделились коллеги (решение №58): смотреть, назначать и делиться дальше, без правки."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal

from .deps import classroom
from .models import Task, Test, TestItem, TestShare


async def share_of(session: AsyncSession, test: Test | None, p: Principal | None) -> TestShare | None:
    """Чужой тест, которым поделились с этим педагогом."""
    if test is None or p is None or test.owner_id == p.user_id or not p.has_any(ROLE_TEACHER):
        return None
    return await session.get(TestShare, (test.id, p.user_id))


async def can_share(session: AsyncSession, test: Test, p: Principal) -> bool:
    """Делиться тестом может автор и тот, с кем им поделились."""
    return test.owner_id == p.user_id or await share_of(session, test, p) is not None


async def task_visible(session: AsyncSession, task: Task, p: Principal | None) -> bool:
    """Задача из теста, которым поделились: педагог видит её целиком (с ответами), даже личную — в банк она не попадает."""
    if p is None or not p.has_any(ROLE_TEACHER):
        return False
    found = await session.scalar(
        select(TestShare.test_id).join(TestItem, TestItem.test_id == TestShare.test_id)
        .where(TestShare.user_id == p.user_id, TestItem.task_id == task.id).limit(1)
    )
    return found is not None


async def are_colleagues(teacher_id: UUID, other_id: UUID) -> bool:
    data = await classroom.get("/internal/colleagues/check", params={"teacher_id": str(teacher_id), "other_id": str(other_id)})
    return bool(data["colleagues"])


def shared_ids(user_id: UUID):
    """Подзапрос: тесты, которыми поделились с пользователем."""
    return select(TestShare.test_id).where(TestShare.user_id == user_id)
