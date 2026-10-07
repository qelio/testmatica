"""Курсы библиотеки (content) глазами assessment: модули, к которым привязаны тесты (решения №43, 44).

Сведения о модуле берутся из content (`/internal/modules/lookup`); права повторяют правила библиотеки:
читать курс — опубликованный всем, черновик — автору и привязанным к нему ученикам; менять — автору,
пока курс в черновике или отклонён (опубликованный — только штатному редактору)."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_MODERATOR, Principal

from . import access
from .deps import content

PUBLISHED, REMOVED = "published", "removed"


async def module_info(module_id: UUID, user_id: UUID | None) -> dict | None:
    """Модуль: названия, курс, его тема, статус и автор; usable — можно ли этому пользователю привязать к нему тест."""
    found = await content.post(
        "/internal/modules/lookup",
        json={"module_ids": [str(module_id)], "user_id": str(user_id or UUID(int=0))},
    )
    return found[0] if found else None


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
