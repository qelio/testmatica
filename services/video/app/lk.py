"""Тонкая обёртка над LiveKit: токены, комнаты, права, запись, вебхуки.

Вся работа с SDK — здесь, чтобы в тестах подменить один объект (FakeLiveKit в conftest).
"""

import json
from dataclasses import dataclass
from datetime import timedelta

from livekit import api

from .config import Settings

# Источники, которые можно публиковать. Экран ученику — только с разрешения педагога (ТЗ, раздел 7).
TEACHER_SOURCES = ["camera", "microphone", "screen_share", "screen_share_audio"]
STUDENT_SOURCES = ["camera", "microphone"]
_SOURCE_ENUM = {
    "camera": api.TrackSource.CAMERA,
    "microphone": api.TrackSource.MICROPHONE,
    "screen_share": api.TrackSource.SCREEN_SHARE,
    "screen_share_audio": api.TrackSource.SCREEN_SHARE_AUDIO,
}


class LiveKitError(Exception):
    """LiveKit не выполнил запрос (комнаты нет, запись не запустилась и т. п.)."""


@dataclass
class WebhookEvent:
    """Нужные нам поля вебхука LiveKit."""

    event: str
    room: str | None
    identity: str | None = None
    participant_sid: str | None = None
    egress_id: str | None = None
    egress_status: str | None = None
    egress_error: str | None = None
    file_size: int | None = None
    file_duration_s: int | None = None


class LiveKit:
    def __init__(self, settings: Settings) -> None:
        self.url = settings.livekit_url
        self.public_url = settings.livekit_public_url
        self.key = settings.livekit_api_key
        self.secret = settings.livekit_api_secret

    def _api(self) -> api.LiveKitAPI:
        return api.LiveKitAPI(self.url, self.key, self.secret)

    def token(self, room: str, identity: str, name: str, teacher: bool, screen_share: bool, ttl: timedelta) -> str:
        sources = TEACHER_SOURCES if teacher else STUDENT_SOURCES + (["screen_share", "screen_share_audio"] if screen_share else [])
        grants = api.VideoGrants(
            room_join=True, room=room, room_admin=teacher, can_publish=True, can_subscribe=True, can_publish_data=True,
            can_publish_sources=sources, can_update_own_metadata=True,
        )
        return (
            api.AccessToken(self.key, self.secret)
            .with_identity(identity)
            .with_name(name)
            .with_metadata(json.dumps({"role": "teacher" if teacher else "student"}))
            .with_grants(grants)
            .with_ttl(ttl)
            .to_jwt()
        )

    async def create_room(self, name: str, max_participants: int) -> None:
        """Идемпотентно: для существующей комнаты LiveKit вернёт её же."""
        async with self._api() as lk:
            await lk.room.create_room(
                api.CreateRoomRequest(name=name, max_participants=max_participants, empty_timeout=300, departure_timeout=20)
            )

    async def delete_room(self, name: str) -> None:
        """Завершить занятие для всех. Если комнаты уже нет — не ошибка."""
        async with self._api() as lk:
            try:
                await lk.room.delete_room(api.DeleteRoomRequest(room=name))
            except api.TwirpError as e:
                if e.code != "not_found":
                    raise

    async def set_screen_share(self, room: str, identity: str, allowed: bool) -> None:
        """Поменять права подключённого ученика; если он не в комнате — применится при следующем входе (в токене)."""
        sources = STUDENT_SOURCES + (["screen_share", "screen_share_audio"] if allowed else [])
        async with self._api() as lk:
            try:
                await lk.room.update_participant(api.UpdateParticipantRequest(
                    room=room, identity=identity,
                    permission=api.ParticipantPermission(
                        can_subscribe=True, can_publish=True, can_publish_data=True,
                        can_publish_sources=[_SOURCE_ENUM[s] for s in sources],
                    ),
                ))
            except api.TwirpError as e:
                if e.code != "not_found":
                    raise

    async def start_recording(self, room: str, filepath: str) -> str:
        """Запись всей комнаты (сетка участников) в MP4; S3 берётся из конфига egress."""
        async with self._api() as lk:
            try:
                info = await lk.egress.start_room_composite_egress(api.RoomCompositeEgressRequest(
                    room_name=room, layout="grid",
                    file_outputs=[api.EncodedFileOutput(file_type=api.EncodedFileType.MP4, filepath=filepath)],
                ))
            except api.TwirpError as e:
                raise LiveKitError(e.message) from e
            return info.egress_id

    async def stop_recording(self, egress_id: str) -> None:
        async with self._api() as lk:
            try:
                await lk.egress.stop_egress(api.StopEgressRequest(egress_id=egress_id))
            except api.TwirpError as e:
                if e.code not in ("not_found", "failed_precondition"):
                    raise

    def parse_webhook(self, body: str, auth_header: str) -> WebhookEvent:
        """Проверить подпись LiveKit и достать нужные поля."""
        event = api.WebhookReceiver(api.TokenVerifier(self.key, self.secret)).receive(body, auth_header)
        out = WebhookEvent(event=event.event, room=event.room.name if event.HasField("room") else None)
        if event.HasField("participant"):
            out.identity, out.participant_sid = event.participant.identity, event.participant.sid
        if event.HasField("egress_info"):
            info = event.egress_info
            out.room = out.room or info.room_name
            out.egress_id, out.egress_status, out.egress_error = info.egress_id, api.EgressStatus.Name(info.status), info.error or None
            if info.file_results:
                f = info.file_results[0]
                out.file_size, out.file_duration_s = int(f.size), int(f.duration // 1_000_000_000)
        return out
