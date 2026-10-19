"""Показ экрана педагога на интерактивной доске (решение №53).

Доска (браузер в кабинете, без входа) создаёт сеанс и показывает код; педагог вводит код у себя и показывает экран.
Код одноразовый и ждёт 10 минут; доска узнаёт статус по своему секрету. Педагог ушёл из комнаты — показ завершён,
доска берёт новый код."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .deps import db, livekit
from .lk import WebhookEvent
from .models import BoardSession

PREFIX = "board-"
CODE_TTL = timedelta(minutes=10)
TOKEN_TTL = timedelta(hours=8)  # хватит на учебный день
MAX_PARTICIPANTS = 4  # педагог, доска и запас на переподключение


def room_name(session_id) -> str:
    return f"{PREFIX}{session_id}"


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def new_secret() -> str:
    return secrets.token_urlsafe(24)


def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def status_of(s: BoardSession, now: datetime) -> str:
    if s.ended_at:
        return "ended"
    if s.paired_at:
        return "live"
    return "expired" if now >= s.expires_at else "waiting"


async def on_webhook(session: AsyncSession, ev: WebhookEvent) -> None:
    """Педагог ушёл из комнаты (закрыл вкладку, остановил показ) или комната закрылась — показ завершён."""
    if not ev.room:
        return
    try:
        sid = UUID(ev.room.removeprefix(PREFIX))
    except ValueError:
        return
    presenter_left = ev.event == "participant_left" and (ev.identity or "").startswith("t-")
    if not (presenter_left or ev.event == "room_finished"):
        return
    s = await session.get(BoardSession, sid, with_for_update=True)
    if s is not None and s.paired_at and not s.ended_at:
        s.ended_at = datetime.now(UTC)


async def cleanup() -> None:
    """Фоновая задача: старые сеансы (код истёк или показ закончился больше суток назад) — удалить."""
    border = datetime.now(UTC) - timedelta(days=1)
    async with db.sessionmaker() as session, session.begin():
        await session.execute(delete(BoardSession).where(
            (BoardSession.ended_at < border) | (BoardSession.paired_at.is_(None) & (BoardSession.expires_at < border))
        ))


async def active_with_code(session: AsyncSession, code: str, now: datetime) -> BoardSession | None:
    return await session.scalar(
        select(BoardSession).where(BoardSession.code == code, BoardSession.paired_at.is_(None), BoardSession.ended_at.is_(None),
                                   BoardSession.expires_at > now).with_for_update()
    )


async def close_room(s: BoardSession) -> None:
    await livekit.delete_room(room_name(s.id))
