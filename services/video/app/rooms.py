"""Жизнь комнаты: лимит времени, закрытие, события LiveKit, хранение записей."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from . import proctoring, storage
from .config import settings
from testmatica_common.plans import BASIC, FREE

from .deps import db, livekit, outbox, plans
from .lk import WebhookEvent
from .models import EXPIRED, FAILED, READY, RECORDING, Connection, Recording, Room

log = logging.getLogger(__name__)


def time_limit_for(lesson: dict, plan: str) -> int | None:
    """Бесплатные занятия на бесплатном тарифе — до 40 минут. Платные и все занятия на «Базовом» — без лимита (решение №5)."""
    return None if lesson.get("paid") or plan == BASIC else settings.free_time_limit_min


async def teacher_plan(teacher_id: UUID) -> str:
    """Тариф педагога; если billing недоступен — действуем по бесплатному, чтобы занятие не сорвалось."""
    return await plans.of(teacher_id, fallback=FREE)


def limit_ends_at(room: Room) -> datetime | None:
    if room.time_limit_min is None or room.started_at is None:
        return None
    return room.started_at + timedelta(minutes=room.time_limit_min)


async def close(session: AsyncSession, room: Room, reason: str) -> None:
    """Закрыть комнату для всех. Запись egress завершится сама, файл придёт вебхуком."""
    await livekit.delete_room(room.livekit_name)
    if room.ended_at is None:
        room.ended_at, room.end_reason = datetime.now(UTC), reason
        await _close_connections(session, room)
        await outbox.event(session, "video.room.ended", _room_data(room) | {"reason": reason})


def _room_data(room: Room) -> dict:
    return {"lesson_id": str(room.lesson_id), "teacher_id": str(room.teacher_id), "kind": room.kind,
            "started_at": room.started_at.isoformat() if room.started_at else None,
            "ended_at": room.ended_at.isoformat() if room.ended_at else None}


async def _close_connections(session: AsyncSession, room: Room) -> None:
    await session.execute(
        update(Connection).where(Connection.room_id == room.id, Connection.left_at.is_(None)).values(left_at=room.ended_at)
    )


def _user_id(identity: str | None) -> UUID | None:
    """Участники — UUID пользователей; у служебных (запись egress) — свои идентификаторы."""
    try:
        return UUID(identity) if identity else None
    except ValueError:
        return None


async def on_webhook(session: AsyncSession, ev: WebhookEvent) -> None:
    now = datetime.now(UTC)
    if ev.event.startswith("egress_"):
        if not await proctoring.on_egress(session, ev, now):
            await _on_egress(session, ev, now)
        return
    if ev.room and ev.room.startswith(proctoring.PREFIX):
        await proctoring.on_webhook(session, ev)
        return
    if not ev.room or not ev.room.startswith("lesson-"):
        return
    room = await session.scalar(select(Room).where(Room.lesson_id == UUID(ev.room.removeprefix("lesson-"))).with_for_update())
    if room is None:
        return
    user = _user_id(ev.identity)
    if ev.event == "participant_joined" and user:
        if room.started_at is None:
            room.started_at = now
            await outbox.event(session, "video.room.started", _room_data(room))
        await session.execute(
            insert(Connection).values(room_id=room.id, user_id=user, livekit_sid=ev.participant_sid, joined_at=now)
            .on_conflict_do_nothing(index_elements=["livekit_sid"])
        )
    elif ev.event == "participant_left" and user:
        await session.execute(
            update(Connection).where(Connection.livekit_sid == ev.participant_sid, Connection.left_at.is_(None)).values(left_at=now)
        )
    elif ev.event == "room_finished" and room.ended_at is None:
        # Все вышли и комната закрылась по таймауту.
        room.ended_at, room.end_reason = now, "empty"
        await _close_connections(session, room)
        await outbox.event(session, "video.room.ended", _room_data(room) | {"reason": "empty"})


async def _on_egress(session: AsyncSession, ev: WebhookEvent, now: datetime) -> None:
    if not ev.egress_id:
        return
    rec = await session.scalar(select(Recording).where(Recording.egress_id == ev.egress_id).with_for_update())
    if rec is None or rec.status != RECORDING:
        return
    if ev.event in ("egress_started", "egress_updated"):
        if ev.egress_status == "EGRESS_ACTIVE" and rec.active_at is None:
            rec.active_at = now  # Chrome запущен, запись идёт
        return
    if ev.event != "egress_ended":
        return
    rec.ended_at = now
    if ev.egress_status == "EGRESS_COMPLETE" and ev.file_size:
        rec.status, rec.size, rec.duration_s = READY, ev.file_size, ev.file_duration_s
        basic = await teacher_plan(rec.teacher_id) == BASIC
        rec.expires_at = now + timedelta(days=settings.basic_recording_days if basic else settings.free_recording_days)
        await outbox.event(session, "video.recording.ready", {
            "recording_id": str(rec.id), "lesson_id": str(rec.lesson_id), "teacher_id": str(rec.teacher_id),
            "viewer_ids": [str(v) for v in rec.viewer_ids], "title": rec.title, "duration_s": rec.duration_s,
        })
        await apply_retention(session, rec.teacher_id)
    else:
        rec.status = FAILED
        rec.error = (ev.egress_error or ev.egress_status or "")[:300]
        log.warning("recording failed", extra={"egress_id": ev.egress_id, "error": ev.egress_error})


async def expire(session: AsyncSession, rec: Recording) -> None:
    rec.status = EXPIRED
    try:
        await storage.delete(rec.key)
    except Exception:  # файл уже удалён или хранилище недоступно — запись всё равно скрываем
        log.warning("recording file not deleted", extra={"recording_id": str(rec.id)})


async def apply_retention(session: AsyncSession, teacher_id: UUID) -> None:
    """Бесплатный тариф: не больше 3 записей у педагога — новая вытесняет самую старую (решение №4)."""
    if await teacher_plan(teacher_id) == BASIC:
        return
    ready = (await session.execute(
        select(Recording).where(Recording.teacher_id == teacher_id, Recording.status == READY)
        .order_by(Recording.started_at.desc()).with_for_update()
    )).scalars().all()
    for rec in ready[settings.free_recordings_keep:]:
        await expire(session, rec)


async def enforce_limits() -> None:
    """Фоновая задача: завершить бесплатные занятия по лимиту времени и удалить просроченные записи."""
    now = datetime.now(UTC)
    async with db.sessionmaker() as session, session.begin():
        rooms = (await session.execute(
            select(Room).where(Room.ended_at.is_(None), Room.started_at.is_not(None), Room.time_limit_min.is_not(None))
            .with_for_update(skip_locked=True)
        )).scalars().all()
        # Педагог мог подключить «Базовый» уже во время занятия — тогда лимит (и таймер в комнате) снимается.
        paid_up = await plans.many({r.teacher_id for r in rooms}, fallback=FREE) if rooms else {}
        for room in rooms:
            if paid_up.get(room.teacher_id) == BASIC:
                room.time_limit_min = None
                continue
            ends = limit_ends_at(room)
            if ends and now >= ends:
                log.info("room time limit reached", extra={"lesson_id": str(room.lesson_id)})
                await close(session, room, "time_limit")
        old = (await session.execute(
            select(Recording).where(Recording.status == READY, Recording.expires_at < now).with_for_update(skip_locked=True)
        )).scalars().all()
        for rec in old:
            await expire(session, rec)
        await proctoring.expire_old(session, now)
