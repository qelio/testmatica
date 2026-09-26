"""Прокторинг тестов: комната на назначение, запись экрана каждого ученика, хранение 14 дней (ТЗ, раздел 7)."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import storage
from .config import settings
from .deps import livekit
from .lk import LiveKitError, WebhookEvent
from .models import EXPIRED, FAILED, READY, RECORDING, ProctorRecording

log = logging.getLogger(__name__)

PREFIX = "proctor-"


def room_name(assignment_id: UUID) -> str:
    return f"{PREFIX}{assignment_id}"


async def on_webhook(session: AsyncSession, ev: WebhookEvent) -> None:
    """Ученик начал показывать экран — пишем эту дорожку в отдельный файл."""
    if ev.event != "track_published" or ev.track_source != "SCREEN_SHARE" or not ev.track_sid:
        return
    meta = ev.metadata or {}
    if meta.get("role") != "student" or not ev.room:
        return
    assignment_id, student_id = UUID(ev.room.removeprefix(PREFIX)), UUID(ev.identity)
    key = f"proctoring/{assignment_id}/{student_id}/{datetime.now(UTC):%Y%m%d-%H%M%S}-{ev.track_sid}"
    try:
        egress_id = await livekit.start_track_recording(ev.room, ev.track_sid, key)
    except LiveKitError as e:
        log.warning("proctor recording not started", extra={"room": ev.room, "error": str(e)})
        return
    session.add(ProctorRecording(
        assignment_id=assignment_id, teacher_id=UUID(meta["teacher_id"]), student_id=student_id,
        attempt_id=UUID(meta["attempt_id"]) if meta.get("attempt_id") else None, title=meta.get("title", "Тест")[:200],
        track_sid=ev.track_sid, egress_id=egress_id, key=key, status=RECORDING,
    ))


async def on_egress(session: AsyncSession, ev: WebhookEvent, now: datetime) -> bool:
    """Запись дорожки закончилась. True — это была запись прокторинга."""
    rec = await session.scalar(select(ProctorRecording).where(ProctorRecording.egress_id == ev.egress_id).with_for_update())
    if rec is None:
        return False
    if ev.event != "egress_ended" or rec.status != RECORDING:
        return True
    rec.ended_at = now
    if ev.egress_status == "EGRESS_COMPLETE" and ev.file_size:
        rec.status, rec.size, rec.duration_s = READY, ev.file_size, ev.file_duration_s
        if ev.file_name and ev.file_name.startswith(rec.key):
            rec.key = ev.file_name  # с расширением, которое выбрал egress
        rec.expires_at = now + timedelta(days=settings.proctor_recording_days)
    else:
        rec.status, rec.error = FAILED, (ev.egress_error or ev.egress_status or "")[:300]
    return True


async def expire_old(session: AsyncSession, now: datetime) -> None:
    old = (await session.execute(
        select(ProctorRecording).where(ProctorRecording.status == READY, ProctorRecording.expires_at < now).with_for_update(skip_locked=True)
    )).scalars().all()
    for rec in old:
        rec.status = EXPIRED
        try:
            await storage.delete(rec.key)
        except Exception:
            log.warning("proctor recording file not deleted", extra={"recording_id": str(rec.id)})
