"""Доставка в реальном времени: WebSocket + Redis pub/sub.

Каждое подключение подписывается на канал своего пользователя (chat:user:<id>).
Сервис после сохранения сообщения публикует его в каналы получателей — так работает
и при нескольких экземплярах сервиса: неважно, к какому из них подключён браузер.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import Iterable
from uuid import UUID

import jwt
from fastapi import APIRouter, WebSocket

from .config import settings
from .deps import redis, verifier

log = logging.getLogger(__name__)
router = APIRouter()


def channel(user_id: UUID | str) -> str:
    return f"chat:user:{user_id}"


async def publish(user_ids: Iterable[UUID], payload: dict) -> None:
    """Сообщение уже сохранено в БД; если Redis недоступен, клиент догрузит историю при переподключении."""
    data = json.dumps(payload, default=str, ensure_ascii=False)
    try:
        async with redis.pipeline(transaction=False) as pipe:
            for uid in set(user_ids):
                pipe.publish(channel(uid), data)
            await pipe.execute()
    except Exception:
        log.exception("realtime publish failed")


@router.websocket("/ws")
async def websocket(ws: WebSocket) -> None:
    """Протокол: клиент первым сообщением шлёт {"type": "auth", "token": "<access token>"},
    сервер отвечает {"type": "ready"} и дальше присылает события {"type": "message", ...}."""
    await ws.accept()
    try:
        first = await asyncio.wait_for(ws.receive_json(), timeout=settings.ws_auth_timeout)
        claims = await verifier.verify(str(first.get("token", ""))) if first.get("type") == "auth" else None
        if not claims or claims.get("typ") != "access":
            raise jwt.InvalidTokenError
    except Exception:  # таймаут, неверный токен, недоступен JWKS, клиент ушёл
        with contextlib.suppress(Exception):
            await ws.close(code=4401, reason="unauthorized")
        return

    user_id = claims["sub"]
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel(user_id))
    await ws.send_json({"type": "ready"})

    async def forward() -> None:
        async for item in pubsub.listen():
            if item.get("type") == "message":
                await ws.send_text(item["data"])

    async def receive() -> None:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})

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
