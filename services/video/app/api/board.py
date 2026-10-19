"""Доска: код на экране кабинета и показ экрана педагога (решение №53)."""

import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_MODERATOR, ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import board, people
from ..deps import auth, db, livekit
from ..models import BoardSession
from ..schemas import BoardCreated, BoardPairIn, BoardPairOut, BoardStatus

router = APIRouter(prefix="/board", tags=["board"])
teacher = auth.require(ROLE_TEACHER, ROLE_MODERATOR)

# Перебор кодов: не больше 10 неверных за 10 минут у одного педагога (кодов миллион, живут 10 минут).
_failures: dict[UUID, deque[float]] = defaultdict(deque)
FAIL_LIMIT, FAIL_WINDOW = 10, 600


def _too_many(user_id: UUID) -> bool:
    q, now = _failures[user_id], time.monotonic()
    while q and now - q[0] > FAIL_WINDOW:
        q.popleft()
    return len(q) >= FAIL_LIMIT


async def _board(session: AsyncSession, session_id: UUID, secret: str, lock: bool = False) -> BoardSession:
    s = await session.get(BoardSession, session_id, with_for_update=lock)
    if s is None or s.secret_hash != board.hash_secret(secret):
        raise ApiError(404, "board_not_found", "Доска не найдена — обновите страницу")
    return s


@router.post("/sessions", response_model=BoardCreated, status_code=201)
async def create(session: AsyncSession = Depends(db.session)) -> BoardCreated:
    """Доска без входа в аккаунт получает код для педагога."""
    now = datetime.now(UTC)
    for _ in range(20):
        code = board.new_code()
        if await board.active_with_code(session, code, now) is None:
            break
    else:
        raise ApiError(503, "board_busy", "Не удалось выдать код — попробуйте ещё раз")
    secret = board.new_secret()
    s = BoardSession(code=code, secret_hash=board.hash_secret(secret), expires_at=now + board.CODE_TTL)
    session.add(s)
    await session.commit()
    return BoardCreated(id=s.id, code=code, secret=secret, expires_at=s.expires_at)


@router.get("/sessions/{session_id}", response_model=BoardStatus)
async def status(
    session_id: UUID, secret: str = Query(min_length=10, max_length=100), session: AsyncSession = Depends(db.session)
) -> BoardStatus:
    """Доска спрашивает, подключился ли педагог; когда да — получает пропуск, чтобы смотреть его экран."""
    s = await _board(session, session_id, secret)
    state = board.status_of(s, datetime.now(UTC))
    out = BoardStatus(status=state, code=s.code, expires_at=s.expires_at, teacher_name=s.teacher_name)
    if state == "live":
        out.url = livekit.public_url
        out.token = livekit.board_token(board.room_name(s.id), f"b-{s.id}", "Доска", presenter=False, ttl=board.TOKEN_TTL)
    return out


@router.post("/sessions/{session_id}/end", status_code=204)
async def end_by_board(
    session_id: UUID, secret: str = Query(min_length=10, max_length=100), session: AsyncSession = Depends(db.session)
) -> None:
    """Доска закрыла показ (кнопка «Новый код»)."""
    s = await _board(session, session_id, secret, lock=True)
    if not s.ended_at:
        s.ended_at = datetime.now(UTC)
        await session.commit()
        if s.paired_at:
            await board.close_room(s)


@router.post("/pair", response_model=BoardPairOut)
async def pair(body: BoardPairIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> BoardPairOut:
    """Педагог вводит код с доски — и получает пропуск, чтобы показать на ней свой экран."""
    if _too_many(principal.user_id):
        raise ApiError(429, "too_many_attempts", "Слишком много неверных кодов — подождите несколько минут")
    now = datetime.now(UTC)
    s = await board.active_with_code(session, body.code, now)
    if s is None:
        _failures[principal.user_id].append(time.monotonic())
        raise ApiError(404, "board_code_invalid", "Код не найден или устарел — проверьте код на доске")
    name = (await people.names(session, [principal.user_id])).get(principal.user_id, "Педагог")
    s.teacher_id, s.teacher_name, s.paired_at = principal.user_id, name, now
    await livekit.create_room(board.room_name(s.id), board.MAX_PARTICIPANTS)
    await session.commit()
    token = livekit.board_token(board.room_name(s.id), f"t-{principal.user_id}", name, presenter=True, ttl=board.TOKEN_TTL)
    return BoardPairOut(id=s.id, url=livekit.public_url, token=token)


@router.post("/sessions/{session_id}/stop", status_code=204)
async def stop(session_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> None:
    """Педагог закончил показ — доска возьмёт новый код."""
    s = await session.get(BoardSession, session_id, with_for_update=True)
    if s is None or s.teacher_id != principal.user_id:
        raise ApiError(404, "board_not_found", "Показ не найден")
    if not s.ended_at:
        s.ended_at = datetime.now(UTC)
        await session.commit()
        await board.close_room(s)
