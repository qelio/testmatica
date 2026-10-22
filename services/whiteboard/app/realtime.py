"""Доска вживую: WebSocket + Redis pub/sub (как в чате).

Клиент первым сообщением шлёт {"type": "auth", "token": "<access token>", "board_id": "…"}; сервер отвечает
{"type": "ready", "role": …, "conn": "<id подключения>"}. Дальше клиент шлёт правки {"type": "ops", "upsert": [...],
"delete": [...]} и черновики {"type": "draft", "item": {...}} — штрих, пока его рисуют (не сохраняется), а сервер
пересылает правки и черновики остальных (с "from" — своё клиент пропускает), смену настроек {"type": "board"} и
{"type": "deleted"}. Курсоры участников: клиент шлёт {"type": "cursor", "x": …, "y": …} (координаты доски; x = null —
курсор ушёл с листа), сервер рассылает их с именем ({"type": "cursor", "from", "user_id", "name", "x", "y"}), а при
отключении — {"type": "leave", "from"}. Доступ ученика пересчитывается при каждой смене настроек: закрыли — соединение закрывается."""

import asyncio
import contextlib
import json
import logging
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, WebSocket
from pydantic import ValidationError
from testmatica_common.errors import ApiError

from . import access, ops, people
from .config import settings
from .deps import db, redis, verifier
from .models import Board
from .schemas import Ops

log = logging.getLogger(__name__)
router = APIRouter()

CLOSE_UNAUTHORIZED, CLOSE_FORBIDDEN, CLOSE_DELETED = 4401, 4403, 4404


async def _role(board_id: UUID, user_id: UUID) -> str | None:
    async with db.sessionmaker() as session:
        board = await session.get(Board, board_id)
        return access.role_of(board, user_id) if board else None


async def _name(user_id: UUID) -> str:
    async with db.sessionmaker() as session:
        return await people.name_of(session, user_id)


def _coord(value: object) -> float | None:
    """Координата курсора: число в разумных пределах, иначе нет курсора."""
    if isinstance(value, bool) or not isinstance(value, int | float) or not abs(value) < 1e7:
        return None
    return round(float(value), 1)


@router.websocket("/ws")
async def websocket(ws: WebSocket) -> None:
    await ws.accept()
    try:
        first = await asyncio.wait_for(ws.receive_json(), timeout=settings.ws_auth_timeout)
        claims = await verifier.verify(str(first.get("token", ""))) if first.get("type") == "auth" else None
        if not claims or claims.get("typ") != "access":
            raise jwt.InvalidTokenError
        board_id = UUID(str(first.get("board_id")))
    except Exception:  # таймаут, неверный токен или доска, недоступен JWKS, клиент ушёл
        with contextlib.suppress(Exception):
            await ws.close(code=CLOSE_UNAUTHORIZED, reason="unauthorized")
        return

    user_id = UUID(claims["sub"])
    role = await _role(board_id, user_id)
    if role is None:
        with contextlib.suppress(Exception):
            await ws.close(code=CLOSE_FORBIDDEN, reason="forbidden")
        return

    conn = uuid4().hex
    state = {"role": role}
    name = await _name(user_id)
    pubsub = redis.pubsub()
    await pubsub.subscribe(ops.channel(board_id))
    await ws.send_json({"type": "ready", "role": role, "conn": conn})

    async def forward() -> None:
        async for item in pubsub.listen():
            if item.get("type") != "message":
                continue
            msg = json.loads(item["data"])
            if msg.get("type") == "deleted":
                await ws.send_json(msg)
                await ws.close(code=CLOSE_DELETED)
                return
            if msg.get("type") == "board":
                state["role"] = await _role(board_id, user_id)
                if state["role"] is None:  # доступ закрыли
                    await ws.close(code=CLOSE_FORBIDDEN)
                    return
                msg["role"] = state["role"]
            await ws.send_json(msg)

    async def receive() -> None:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "ping":
                await ws.send_json({"type": "pong"})
            elif kind == "cursor":  # курсор видно у всех, кто на доске, в том числе только смотрящих
                x, y = _coord(msg.get("x")), _coord(msg.get("y"))
                await ops.publish(board_id, {"type": "cursor", "from": conn, "user_id": str(user_id), "name": name,
                                             "x": x if y is not None else None, "y": y if x is not None else None})
            elif kind in ("ops", "draft") and state["role"] == "read":
                await ws.send_json({"type": "error", "code": "read_only", "message": "Доска открыта только для просмотра"})
            elif kind == "draft":
                await ops.publish(board_id, {"type": "draft", "from": conn, "item": msg.get("item")})
            elif kind == "ops":
                await _save(msg)

    async def _save(msg: dict) -> None:
        try:
            body = Ops.model_validate(msg)
            async with db.sessionmaker() as session, session.begin():
                board = await session.get(Board, board_id, with_for_update=True)
                if board is None or access.role_of(board, user_id) in (None, "read"):
                    raise ApiError(403, "read_only", "Доска открыта только для просмотра")
                await ops.apply(session, board, user_id, body)
        except (ValidationError, ApiError) as e:
            message = e.message if isinstance(e, ApiError) else "Некорректная правка"
            await ws.send_json({"type": "error", "code": getattr(e, "code", "invalid_ops"), "message": message, "ref": msg.get("ref")})
            return
        await ops.publish(board_id, {"type": "ops", "from": conn, **body.model_dump(mode="json")})
        if msg.get("ref"):
            await ws.send_json({"type": "ack", "ref": msg["ref"]})

    tasks = [asyncio.create_task(forward()), asyncio.create_task(receive())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(BaseException):
                await task
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe()
            await pubsub.aclose()
        with contextlib.suppress(Exception):
            await ops.publish(board_id, {"type": "leave", "from": conn})
