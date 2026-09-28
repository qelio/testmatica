"""Кто что видит и кто что может менять в библиотеке."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_MODERATOR, ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .models import PENDING, PRIVATE, PUBLISHED, REJECTED, REMOVED, Material, Node, RelLink


def is_staff(principal: Principal | None) -> bool:
    return principal is not None and principal.has_any(ROLE_MODERATOR)


async def linked(session: AsyncSession, teacher_id: UUID, student_id: UUID) -> bool:
    return await session.get(RelLink, (teacher_id, student_id)) is not None


async def can_read(session: AsyncSession, course: Node, principal: Principal | None) -> bool:
    """Опубликованное — всем, включая гостей. Остальное — автору, модераторам
    и привязанным к автору ученикам (приватная библиотека педагога)."""
    if course.status == PUBLISHED:
        return True
    if principal is None:
        return False
    if course.owner_id == principal.user_id or is_staff(principal):
        return True
    if course.status == REMOVED:
        return False  # снятый администратором курс ученикам автора тоже не показываем
    return await linked(session, course.owner_id, principal.user_id)


def can_edit(course: Node, principal: Principal | None) -> bool:
    """Автор правит курс, пока он в приватной библиотеке или отклонён. На модерации — заблокирован.
    Опубликованный курс может править только штатный редактор (модератор), которому он принадлежит."""
    if principal is None or course.owner_id != principal.user_id:
        return False
    if course.status in (PRIVATE, REJECTED):
        return True
    return course.status == PUBLISHED and is_staff(principal)


def can_author(principal: Principal) -> bool:
    return principal.has_any(ROLE_TEACHER, ROLE_MODERATOR)


async def load_node(session: AsyncSession, node_id: UUID, lock: bool = False) -> tuple[Node, Node]:
    node = await session.get(Node, node_id, with_for_update=lock)
    if node is None:
        raise ApiError(404, "not_found", "Не найдено")
    course = node if node.kind == "course" else await session.get(Node, node.course_id, with_for_update=lock)
    return node, course


async def readable_node(session: AsyncSession, node_id: UUID, principal: Principal | None) -> tuple[Node, Node]:
    node, course = await load_node(session, node_id)
    if not await can_read(session, course, principal):
        raise ApiError(404, "not_found", "Не найдено")
    return node, course


async def editable_node(session: AsyncSession, node_id: UUID, principal: Principal) -> tuple[Node, Node]:
    node, course = await load_node(session, node_id, lock=True)
    if not await can_read(session, course, principal):
        raise ApiError(404, "not_found", "Не найдено")
    if not can_edit(course, principal):
        if course.status == PENDING:
            raise ApiError(409, "course_pending", "Курс на модерации — изменения недоступны до решения модератора")
        raise ApiError(403, "forbidden", "Этот курс нельзя изменять")
    return node, course


async def editable_material(session: AsyncSession, material_id: UUID, principal: Principal) -> tuple[Material, Node]:
    material = await session.get(Material, material_id, with_for_update=True)
    if material is None:
        raise ApiError(404, "not_found", "Материал не найден")
    _, course = await editable_node(session, material.course_id, principal)
    return material, course


async def owner_linked_students(session: AsyncSession, teacher_id: UUID) -> set[UUID]:
    rows = await session.execute(select(RelLink.student_id).where(RelLink.teacher_id == teacher_id))
    return set(rows.scalars())
