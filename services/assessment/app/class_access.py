"""Работы класса у всех его педагогов (решение №61): владелец класса и коллеги с правом «Работы класса» видят и
ведут любую работу, выданную классу, — ход вживую, проверка, результаты, — кто бы её ни назначил."""

import logging
from uuid import UUID

from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .deps import classroom
from .models import Assignment

log = logging.getLogger(__name__)

OWNER, CLASS_WORKS = "owner", "class_works"


def _runs_works(permissions: list[str]) -> bool:
    return OWNER in permissions or CLASS_WORKS in permissions


async def can_run(a: Assignment, p: Principal) -> bool:
    """Педагог (не автор работы) ведёт работу класса: он владелец класса или коллега с правом «Работы класса»."""
    return p.has_any(ROLE_TEACHER) and await runs(a, p.user_id)


async def runs(a: Assignment, user_id: UUID) -> bool:
    """То же по id пользователя (прокторинг: video знает только его): доступ к классу есть только у педагогов."""
    if a.target_type != "group" or a.teacher_id == user_id:
        return False
    return await runs_class(a.target_id, user_id)


async def runs_class(group_id: UUID, user_id: UUID) -> bool:
    """Педагог ведёт работы класса: владелец или коллега с правом «Работы класса»."""
    try:
        info = await classroom.get(f"/internal/groups/{group_id}", params={"teacher_id": str(user_id)})
    except ApiError as e:
        if e.status == 404:
            return False
        raise
    return _runs_works(info.get("permissions", []))


async def watchers(a: Assignment) -> list[str]:
    """Кому ещё показывать ход работы вживую: педагоги класса с этим правом, кроме автора. Ошибка — никому."""
    if a.target_type != "group":
        return []
    try:
        info = await classroom.get(f"/internal/groups/{a.target_id}", params={"teacher_id": str(a.teacher_id)})
    except ApiError:
        log.warning("class teachers unavailable", extra={"assignment_id": str(a.id)})
        return []
    return [t["teacher_id"] for t in info.get("teachers", []) if t["teacher_id"] != str(a.teacher_id) and _runs_works(t["permissions"])]
