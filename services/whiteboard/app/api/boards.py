"""Доски педагога и учеников (решение №60): к занятию (одна на занятие) и свободные."""

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import access, ops, people
from ..deps import auth, db, schedule
from ..models import ACCESS_NONE, Board, Item
from ..schemas import BoardCreate, BoardOut, BoardSummary, BoardUpdate, ItemOut, Ops

router = APIRouter(tags=["boards"])
teacher = auth.require(ROLE_TEACHER)


async def summary(session: AsyncSession, board: Board, role: str, count: int | None = None) -> BoardSummary:
    if count is None:
        count = await session.scalar(select(func.count()).select_from(Item).where(Item.board_id == board.id))
    return BoardSummary(
        id=board.id, title=board.title, owner_id=board.owner_id, owner_name=await people.name_of(session, board.owner_id),
        lesson_id=board.lesson_id, lesson_starts_at=board.lesson_starts_at, group_id=board.group_id, student_id=board.student_id,
        target_title=board.target_title, access=board.access, paper_style=board.paper_style, paper_color=board.paper_color,
        role=role, items_count=count or 0, updated_at=board.updated_at,
    )


async def board_out(session: AsyncSession, board: Board, role: str) -> BoardOut:
    items = (await session.execute(select(Item).where(Item.board_id == board.id).order_by(Item.z, Item.updated_at))).scalars().all()
    base = await summary(session, board, role, len(items))
    return BoardOut(**base.model_dump(), items=[ItemOut(id=i.id, kind=i.kind, data=i.data, z=i.z, author_id=i.author_id) for i in items])


@router.get("/boards", response_model=list[BoardSummary])
async def list_boards(
    kind: str = Query("all", pattern="^(all|lesson|free)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> list[BoardSummary]:
    """Свои доски (педагог) и доски педагогов, открытые ученику. Сначала недавние."""
    me = principal.user_id
    query = select(Board).where(or_(Board.owner_id == me, Board.member_ids.contains([me]) & (Board.access != ACCESS_NONE)))
    if kind == "lesson":
        query = query.where(Board.lesson_id.is_not(None))
    elif kind == "free":
        query = query.where(Board.lesson_id.is_(None))
    boards = (await session.execute(query.order_by(Board.updated_at.desc(), Board.id.desc()).offset(offset).limit(limit))).scalars().all()
    counts = dict((await session.execute(
        select(Item.board_id, func.count()).where(Item.board_id.in_([b.id for b in boards])).group_by(Item.board_id)
    )).all()) if boards else {}
    return [await summary(session, b, access.role_of(b, me), counts.get(b.id, 0)) for b in boards]


@router.post("/boards", response_model=BoardOut, status_code=201)
async def create_board(body: BoardCreate, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> BoardOut:
    """Свободная доска — без занятия; по желанию видна классу или ученику."""
    if body.group_id and body.student_id:
        raise ApiError(422, "invalid_target", "Выберите класс или ученика")
    members, title = await access.target_members(principal.user_id, body.group_id, body.student_id)
    if body.student_id:
        title = await people.name_of(session, body.student_id)
    board = Board(owner_id=principal.user_id, title=body.title, group_id=body.group_id, student_id=body.student_id,
                  target_title=title, member_ids=members, access=body.access)
    session.add(board)
    await session.commit()
    return await board_out(session, board, "owner")


MSK = ZoneInfo("Europe/Moscow")


def _lesson_title(lesson: dict) -> str:
    """«Алгебра — 21.10.2026: Дроби»; дата — по Москве (часового пояса педагога у занятия нет)."""
    when = datetime.fromisoformat(lesson["starts_at"]).astimezone(MSK)
    return f"{lesson['subject'] or 'Занятие'} — {when:%d.%m.%Y}" + (f": {lesson['topic']}" if lesson.get("topic") else "")


@router.post("/lessons/{lesson_id}/board", response_model=BoardSummary)
async def open_lesson_board(lesson_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> BoardSummary:
    """Доска занятия: педагог открывает её с карточки занятия — первый раз она создаётся."""
    lesson = await schedule.get(f"/internal/lessons/{lesson_id}", params={"teacher_id": str(principal.user_id)})
    board = await session.scalar(select(Board).where(Board.lesson_id == lesson_id).with_for_update())
    if board is None:
        group_id = UUID(lesson["group_id"]) if lesson.get("group_id") else None
        student_id = UUID(lesson["student_id"]) if lesson.get("student_id") else None
        target = lesson.get("group_title") or (await people.name_of(session, student_id) if student_id else None)
        board = Board(owner_id=principal.user_id, title=_lesson_title(lesson), lesson_id=lesson_id,
                      lesson_starts_at=datetime.fromisoformat(lesson["starts_at"]), group_id=group_id, student_id=student_id,
                      target_title=target)
        session.add(board)
    board.member_ids = [UUID(s) for s in lesson["participant_ids"]]
    await session.commit()
    return await summary(session, board, "owner")


@router.get("/lessons/{lesson_id}/board", response_model=BoardSummary)
async def lesson_board(lesson_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> BoardSummary:
    """Доска занятия для ученика (и педагога): 404 — педагог её не открывал или закрыл доступ."""
    board = await session.scalar(select(Board).where(Board.lesson_id == lesson_id))
    role = access.role_of(board, principal.user_id) if board else None
    if role is None:
        raise ApiError(404, "board_not_found", "Доски к этому занятию нет")
    return await summary(session, board, role)


@router.get("/boards/{board_id}", response_model=BoardOut)
async def get_board(board_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> BoardOut:
    board, role = await access.load(session, board_id, principal.user_id)
    if role == "owner":  # состав класса мог поменяться
        before = list(board.member_ids or [])
        await access.refresh_members(board)
        if list(board.member_ids or []) != before:
            await session.commit()
    return await board_out(session, board, role)


@router.patch("/boards/{board_id}", response_model=BoardSummary)
async def update_board(
    board_id: UUID, body: BoardUpdate, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> BoardSummary:
    """Название, доступ учеников, бумага; у свободной доски — кому видна."""
    board = await access.owned(session, board_id, principal.user_id)
    for field in ("title", "access", "paper_style", "paper_color"):
        if (value := getattr(body, field)) is not None:
            setattr(board, field, value)
    if body.target is not None:
        if board.lesson_id:
            raise ApiError(422, "lesson_board", "Доска занятия видна ученикам этого занятия")
        group_id, student_id = body.target.get("group_id"), body.target.get("student_id")
        if group_id and student_id:
            raise ApiError(422, "invalid_target", "Выберите класс или ученика")
        board.member_ids, title = await access.target_members(board.owner_id, group_id, student_id)
        board.group_id, board.student_id = group_id, student_id
        board.target_title = await people.name_of(session, student_id) if student_id else title
    board.updated_at = datetime.now(UTC)
    await session.commit()
    out = await summary(session, board, "owner")
    # Открытые доски узнают о новом доступе и бумаге сразу.
    await ops.publish(board.id, {"type": "board", "board": out.model_dump(mode="json", exclude={"role"})})
    return out


@router.delete("/boards/{board_id}", status_code=204)
async def delete_board(board_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> None:
    board = await access.owned(session, board_id, principal.user_id)
    await session.delete(board)
    await session.commit()
    await ops.publish(board_id, {"type": "deleted"})


@router.post("/boards/{board_id}/ops", status_code=204)
async def apply_ops(
    board_id: UUID, body: Ops, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> None:
    """Правка без WebSocket (например, вставка большой картинки или запасной путь при плохой связи)."""
    board, role = await access.load(session, board_id, principal.user_id, lock=True)
    if role == "read":
        raise ApiError(403, "read_only", "Доска открыта только для просмотра")
    await ops.apply(session, board, principal.user_id, body)
    await session.commit()
    await ops.publish(board.id, {"type": "ops", "from": None, **body.model_dump(mode="json")})
