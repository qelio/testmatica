"""Правки доски: сохраняются в БД и рассылаются всем, кто её открыл (через Redis — неважно, к какому экземпляру
сервиса подключён браузер)."""

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError

from .config import settings
from .deps import redis
from .models import Board, Item
from .schemas import Ops

log = logging.getLogger(__name__)


def channel(board_id: UUID | str) -> str:
    return f"whiteboard:board:{board_id}"


async def publish(board_id: UUID, payload: dict) -> None:
    """Правка уже сохранена; если Redis недоступен, остальные увидят её, когда переоткроют доску."""
    try:
        await redis.publish(channel(board_id), json.dumps(payload, default=str, ensure_ascii=False))
    except Exception:
        log.exception("whiteboard publish failed")


async def apply(session: AsyncSession, board: Board, author_id: UUID, ops: Ops) -> None:
    if len(ops.upsert) + len(ops.delete) > settings.max_batch:
        raise ApiError(422, "batch_too_large", "Слишком большая правка — разбейте на части")
    for item in ops.upsert:
        if len(json.dumps(item.data, ensure_ascii=False)) > settings.max_item_bytes:
            raise ApiError(422, "item_too_large", "Объект слишком большой")
    if ops.upsert:
        count = await session.scalar(select(func.count()).select_from(Item).where(Item.board_id == board.id))
        if count + len(ops.upsert) > settings.max_items:
            raise ApiError(409, "board_full", "На доске слишком много объектов — начните новую доску")
        stmt = insert(Item).values([
            {"id": i.id, "board_id": board.id, "kind": i.kind, "data": i.data, "z": i.z, "author_id": author_id}
            for i in ops.upsert
        ])
        # Объект с тем же id на другой доске не трогаем.
        await session.execute(stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={"kind": stmt.excluded.kind, "data": stmt.excluded.data, "z": stmt.excluded.z, "updated_at": func.now()},
            where=Item.board_id == board.id,
        ))
    if ops.delete:
        await session.execute(delete(Item).where(Item.board_id == board.id, Item.id.in_(ops.delete)))
    board.updated_at = datetime.now(UTC)
