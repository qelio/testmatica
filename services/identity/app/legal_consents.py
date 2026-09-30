"""Запись и проверка согласий (соглашение и обработка ПД) — текущих редакций из legal.CURRENT."""

from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import sessions
from .deps import outbox
from .legal import CURRENT
from .models import Consent


async def record(session: AsyncSession, user_id: UUID, request: Request, source: str, by_representative: bool = False) -> None:
    ip = sessions.client_ip(request)
    agent = (request.headers.get("user-agent") or "")[:400] or None
    for kind, version in CURRENT.items():
        session.add(Consent(user_id=user_id, type=kind, version=version, ip=ip, user_agent=agent, source=source,
                            by_representative=by_representative))
    # В аудит — факт и версии, без IP и браузера (они хранятся здесь).
    await outbox.event(session, "identity.user.consented",
                       {"user_id": str(user_id), "versions": CURRENT, "source": source, "by_representative": by_representative},
                       actor_id=user_id)


async def required(session: AsyncSession, user_id: UUID) -> bool:
    """True, если нет согласия хотя бы с одной текущей редакцией."""
    rows = set((await session.execute(
        select(Consent.type, Consent.version).where(Consent.user_id == user_id)
    )).all())
    return any((kind, version) not in rows for kind, version in CURRENT.items())
