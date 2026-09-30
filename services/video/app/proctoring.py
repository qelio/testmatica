"""Прокторинг тестов: комната на назначение, запись экрана каждого ученика, хранение 14 дней (ТЗ, раздел 7)."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import storage
from .config import settings
from testmatica_common.errors import ApiError

from .deps import assessment, livekit, outbox
from .lk import LiveKitError, WebhookEvent
from .models import EXPIRED, FAILED, READY, RECORDING, ProctorRecording

log = logging.getLogger(__name__)

PREFIX = "proctor-"


def room_name(assignment_id: UUID) -> str:
    return f"{PREFIX}{assignment_id}"


async def _screen(session: AsyncSession, ev: WebhookEvent, sharing: bool) -> None:
    """Показ экрана начался или прекратился — сообщаем assessment: без показа ответы в тесте не принимаются.
    Источник — сервер видеосвязи, а не страница ученика (её можно подправить)."""
    try:
        student_id = UUID(ev.identity or "")
    except ValueError:
        return  # служебный участник (запись)
    await outbox.event(session, "video.proctor.screen", {
        "assignment_id": ev.room.removeprefix(PREFIX), "student_id": str(student_id), "sharing": sharing,
        "at": datetime.now(UTC).isoformat(),
    })


async def on_webhook(session: AsyncSession, ev: WebhookEvent) -> None:
    """Ученик начал показывать экран — пишем эту дорожку в отдельный файл.
    В событиях о дорожках LiveKit передаёт об участнике только идентификатор (без метаданных пропуска),
    поэтому роль и попытку уточняем у assessment."""
    if not ev.room or not ev.identity:
        return
    # Показ прекратился: остановил дорожку или вышел из комнаты (закрыл вкладку, пропала сеть).
    if (ev.event == "track_unpublished" and ev.track_source == "SCREEN_SHARE") or ev.event == "participant_left":
        await _screen(session, ev, sharing=False)
        return
    if ev.event != "track_published":
        return
    if ev.track_source != "SCREEN_SHARE" or not ev.track_sid:
        log.info("proctor track skipped", extra={"room": ev.room, "source": ev.track_source})
        return
    assignment_id = UUID(ev.room.removeprefix(PREFIX))
    try:
        access = await assessment.get(f"/internal/proctoring/{assignment_id}", params={"user_id": ev.identity})
    except ApiError as e:
        log.warning("proctor access check failed", extra={"room": ev.room, "error": e.message})
        return
    if access["role"] != "student":
        return
    await _screen(session, ev, sharing=True)
    student_id = UUID(ev.identity)
    key = f"proctoring/{assignment_id}/{student_id}/{datetime.now(UTC):%Y%m%d-%H%M%S}-{ev.track_sid}"
    try:
        egress_id = await livekit.start_track_recording(ev.room, ev.track_sid, key)
    except LiveKitError as e:
        log.warning("proctor recording not started", extra={"room": ev.room, "error": str(e)})
        return
    session.add(ProctorRecording(
        assignment_id=assignment_id, teacher_id=UUID(access["teacher_id"]), student_id=student_id,
        attempt_id=UUID(access["attempt_id"]) if access.get("attempt_id") else None, title=access["title"][:200],
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
        # Если egress не дал длительность — по нашим отметкам начала и конца записи.
        rec.status, rec.size = READY, ev.file_size
        rec.duration_s = ev.file_duration_s or max(1, int((now - rec.started_at).total_seconds()))
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
