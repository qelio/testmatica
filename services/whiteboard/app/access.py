"""Кто видит доску и кто на ней рисует (решение №60)."""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError

from .deps import classroom, schedule
from .models import ACCESS_EDIT, ACCESS_NONE, Board

log = logging.getLogger(__name__)


def role_of(board: Board, user_id: UUID) -> str | None:
    """owner — педагог; ученики занятия (класса) — по доступу: edit рисуют, read смотрят, none — не видят."""
    if board.owner_id == user_id:
        return "owner"
    if user_id in (board.member_ids or []) and board.access != ACCESS_NONE:
        return "edit" if board.access == ACCESS_EDIT else "read"
    return None


async def load(session: AsyncSession, board_id: UUID, user_id: UUID, lock: bool = False) -> tuple[Board, str]:
    board = await session.get(Board, board_id, with_for_update=lock)
    role = role_of(board, user_id) if board is not None else None
    if board is None or role is None:
        raise ApiError(404, "board_not_found", "Доска не найдена")
    return board, role


async def owned(session: AsyncSession, board_id: UUID, user_id: UUID) -> Board:
    board, role = await load(session, board_id, user_id, lock=True)
    if role != "owner":
        raise ApiError(403, "forbidden", "Менять настройки доски может только педагог")
    return board


async def target_members(owner_id: UUID, group_id: UUID | None, student_id: UUID | None) -> tuple[list[UUID], str | None]:
    """Ученики класса или ученик педагога и подпись «кому». 404 от classroom — не его класс или ученик."""
    if group_id:
        group = await classroom.get(f"/internal/groups/{group_id}", params={"teacher_id": str(owner_id)})
        return [UUID(s) for s in group["member_ids"]], group["title"]
    if student_id:
        link = await classroom.get("/internal/links", params={"teacher_id": str(owner_id), "student_id": str(student_id)})
        return ([student_id] if link["active"] else []), None
    return [], None


async def refresh_members(board: Board) -> None:
    """Обновить состав: ученики занятия или текущий состав класса. Ошибка соседнего сервиса — оставляем прежний."""
    try:
        if board.lesson_id:
            lesson = await schedule.get(f"/internal/lessons/{board.lesson_id}", params={"teacher_id": str(board.owner_id)})
            board.member_ids = [UUID(s) for s in lesson["participant_ids"]]
        elif board.group_id or board.student_id:
            board.member_ids, _ = await target_members(board.owner_id, board.group_id, board.student_id)
    except ApiError as e:
        if e.status != 404:
            log.warning("board members not refreshed", extra={"board_id": str(board.id), "code": e.code})
