"""Вебхуки LiveKit. Путь /internal наружу не публикуется; подлинность — по подписи LiveKit."""

import logging

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError

from .. import rooms
from ..deps import db, livekit

router = APIRouter(prefix="/internal", tags=["internal"])
log = logging.getLogger(__name__)


@router.post("/webhooks/livekit", status_code=204)
async def livekit_webhook(
    request: Request, authorization: str = Header(""), session: AsyncSession = Depends(db.session)
) -> None:
    body = (await request.body()).decode()
    try:
        event = livekit.parse_webhook(body, authorization)
    except Exception as e:
        raise ApiError(401, "invalid_signature", "Неверная подпись вебхука") from e
    await rooms.on_webhook(session, event)
    await session.commit()
