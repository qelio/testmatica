"""Видеокомната занятия: вход (токен LiveKit), права на экран, запись, завершение."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal
from testmatica_common.errors import ApiError
from testmatica_common.ids import uuid7

from .. import people, rooms
from ..config import settings
from ..deps import auth, db, livekit, outbox, schedule
from ..lk import LiveKitError
from ..models import RECORDING, Recording, Room
from ..schemas import JoinOut, RoomOut, ScreenShareIn

router = APIRouter(prefix="/rooms", tags=["rooms"])


async def _lesson(lesson_id: UUID, p: Principal) -> tuple[dict, bool]:
    """Занятие и роль: педагог занятия или его участник. Остальным — «не найдено»."""
    lesson = await schedule.get(f"/internal/lessons/{lesson_id}/room")
    if lesson["teacher_id"] == str(p.user_id):
        return lesson, True
    if str(p.user_id) in lesson["participant_ids"]:
        return lesson, False
    raise ApiError(404, "lesson_not_found", "Занятие не найдено")


async def _room_for(session: AsyncSession, lesson: dict, lock: bool = False) -> Room:
    """Комната занятия; создаётся при первом обращении педагога или ученика."""
    lesson_id = UUID(lesson["id"])
    room = await session.scalar(select(Room).where(Room.lesson_id == lesson_id).with_for_update() if lock else select(Room).where(Room.lesson_id == lesson_id))
    if room is None:
        group = lesson["kind"] == "group"
        title = lesson.get("group_title") or "Занятие" if group else "Индивидуальное занятие"
        room = Room(
            lesson_id=lesson_id, teacher_id=UUID(lesson["teacher_id"]), kind=lesson["kind"],
            group_id=UUID(lesson["group_id"]) if lesson.get("group_id") else None,
            title=f"{title}{' · ' + lesson['subject'] if lesson.get('subject') else ''}",
            # +1 место — для невидимого участника записи (egress).
            max_participants=(settings.group_capacity if group else settings.individual_capacity) + 1,
            time_limit_min=await rooms.time_limit_for(lesson, await rooms.teacher_plan(UUID(lesson["teacher_id"]))),
        )
        session.add(room)
        await session.flush()
    return room


async def room_out(session: AsyncSession, room: Room, lesson: dict, is_teacher: bool) -> RoomOut:
    rec = await session.scalar(select(Recording).where(Recording.room_id == room.id, Recording.status == RECORDING))
    state = None if rec is None else "stopping" if rec.stop_requested_at else "active" if rec.active_at else "starting"
    status = "ended" if room.ended_at else "active" if room.started_at else "waiting"
    return RoomOut(
        lesson_id=room.lesson_id, title=room.title, is_teacher=is_teacher, status=status, started_at=room.started_at,
        lesson_ends_at=lesson["ends_at"], limit_ends_at=rooms.limit_ends_at(room), end_reason=room.end_reason,
        screen_share=room.screen_share, recording=state, max_participants=room.max_participants - 1,
        external_url=lesson.get("video_url"),
    )


@router.get("/{lesson_id}", response_model=RoomOut)
async def get_room(lesson_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> RoomOut:
    """Состояние комнаты для карточки занятия: ждёт, идёт, завершена; идёт ли запись."""
    lesson, is_teacher = await _lesson(lesson_id, principal)
    room = await _room_for(session, lesson)
    await session.commit()
    return await room_out(session, room, lesson, is_teacher)


@router.post("/{lesson_id}/join", response_model=JoinOut)
async def join(lesson_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> JoinOut:
    """Пропуск в комнату: только педагог и ученики занятия, в окне вокруг времени занятия."""
    lesson, is_teacher = await _lesson(lesson_id, principal)
    if lesson["status"] != "scheduled":
        raise ApiError(409, "lesson_cancelled", "Занятие отменено")
    now = datetime.now(UTC)
    starts, ends = datetime.fromisoformat(lesson["starts_at"]), datetime.fromisoformat(lesson["ends_at"])
    before = settings.teacher_join_before_min if is_teacher else settings.student_join_before_min
    if now < starts - timedelta(minutes=before):
        raise ApiError(409, "too_early", f"Комната откроется за {before} минут до начала занятия")
    if now > ends + timedelta(minutes=settings.join_after_end_min):
        raise ApiError(409, "lesson_over", "Занятие уже закончилось")

    room = await _room_for(session, lesson, lock=True)
    if room.ended_at:
        if room.end_reason == "time_limit":
            raise ApiError(409, "time_limit", f"Время бесплатного занятия ({room.time_limit_min} минут) истекло")
        if room.end_reason == "teacher" and not is_teacher:
            raise ApiError(409, "room_closed", "Педагог завершил занятие")
        # Педагог вернулся или комната закрылась, опустев, — открываем снова (время считается от первого входа).
        room.ended_at, room.end_reason = None, None
    await livekit.create_room(room.livekit_name, room.max_participants)

    name = (await people.names(session, [principal.user_id])).get(principal.user_id, people.UNKNOWN_NAME)
    ttl = max(ends + timedelta(minutes=settings.join_after_end_min) - now, timedelta(hours=1))
    token = livekit.token(
        room.livekit_name, str(principal.user_id), name, teacher=is_teacher,
        screen_share=principal.user_id in room.screen_share, ttl=ttl,
    )
    await session.commit()
    return JoinOut(url=livekit.public_url, token=token, room=await room_out(session, room, lesson, is_teacher))


async def _teacher_room(session: AsyncSession, lesson_id: UUID, p: Principal) -> tuple[Room, dict]:
    lesson, is_teacher = await _lesson(lesson_id, p)
    if not is_teacher:
        raise ApiError(403, "forbidden", "Это может только педагог")
    return await _room_for(session, lesson, lock=True), lesson


@router.post("/{lesson_id}/screen-share", response_model=RoomOut)
async def screen_share(
    lesson_id: UUID, body: ScreenShareIn, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> RoomOut:
    """Педагог разрешает (или запрещает) ученику показывать свой экран."""
    room, lesson = await _teacher_room(session, lesson_id, principal)
    if str(body.student_id) not in lesson["participant_ids"]:
        raise ApiError(404, "student_not_found", "Ученик не участвует в занятии")
    allowed = [s for s in room.screen_share if s != body.student_id] + ([body.student_id] if body.allowed else [])
    room.screen_share = allowed
    await livekit.set_screen_share(room.livekit_name, str(body.student_id), body.allowed)
    await session.commit()
    return await room_out(session, room, lesson, True)


@router.post("/{lesson_id}/recording", response_model=RoomOut)
async def recording(
    lesson_id: UUID,
    action: str = Query(pattern="^(start|stop)$"),
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> RoomOut:
    """Запись занятия: включает и выключает педагог. Файл появится после остановки (обработка — до пары минут)."""
    room, lesson = await _teacher_room(session, lesson_id, principal)
    active = await session.scalar(select(Recording).where(Recording.room_id == room.id, Recording.status == RECORDING))
    if action == "start":
        if active:
            raise ApiError(409, "already_recording", "Запись уже идёт")
        if room.ended_at or not room.started_at:
            raise ApiError(409, "room_not_active", "Запись можно включить, когда занятие идёт")
        rec_id = uuid7()
        key = f"lessons/{lesson_id}/{rec_id}.mp4"
        try:
            egress_id = await livekit.start_recording(room.livekit_name, key)
        except LiveKitError as e:
            raise ApiError(409, "recording_failed", f"Не удалось включить запись: {e}") from e
        started = datetime.now(UTC)
        session.add(Recording(
            id=rec_id, room_id=room.id, lesson_id=room.lesson_id, teacher_id=room.teacher_id, egress_id=egress_id, key=key,
            title=f"{room.title} · {datetime.fromisoformat(lesson['starts_at']).strftime('%d.%m.%Y')}",
            viewer_ids=[UUID(s) for s in lesson["participant_ids"]], started_at=started,
        ))
    else:
        if not active or active.stop_requested_at:
            raise ApiError(409, "not_recording", "Запись не идёт")
        # Страховка: если вебхук о старте потерялся, через полминуты остановить всё же можно.
        if active.active_at is None and datetime.now(UTC) - active.started_at < timedelta(seconds=30):
            # Остановка до старта записи оставляет пустой файл (egress прерывается) — просим подождать.
            raise ApiError(409, "recording_starting", "Запись ещё запускается — подождите несколько секунд")
        await livekit.stop_recording(active.egress_id)
        active.stop_requested_at = datetime.now(UTC)
    await session.commit()
    return await room_out(session, room, lesson, True)


@router.post("/{lesson_id}/end", response_model=RoomOut)
async def end(lesson_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> RoomOut:
    """Завершить занятие для всех (запись, если шла, остановится и сохранится)."""
    room, lesson = await _teacher_room(session, lesson_id, principal)
    await rooms.close(session, room, "teacher")
    await session.commit()
    return await room_out(session, room, lesson, True)
