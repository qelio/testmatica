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
    metadata: dict | None = None  # метаданные участника из токена (роль, попытка)
    track_sid: str | None = None
    track_source: str | None = None  # CAMERA / SCREEN_SHARE / ...
    file_name: str | None = None  # итоговый путь файла (расширение выбирает egress по кодеку)


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

    def proctor_token(self, room: str, identity: str, name: str, teacher: bool, metadata: dict, ttl: timedelta) -> str:
        """Прокторинг: ученик только показывает экран (и камеру по запросу), чужого не видит; педагог только смотрит
        и шлёт сигналы (запрос камеры), сам невидим."""
        grants = api.VideoGrants(
            room_join=True, room=room, can_publish=not teacher, can_subscribe=teacher, can_publish_data=True,
            can_publish_sources=[] if teacher else ["screen_share", "camera"], hidden=teacher,
        )
        return (
            api.AccessToken(self.key, self.secret)
            .with_identity(identity)
            .with_name(name)
            .with_metadata(json.dumps(metadata))
            .with_grants(grants)
            .with_ttl(ttl)
            .to_jwt()
        )

    def board_token(self, room: str, identity: str, name: str, presenter: bool, ttl: timedelta) -> str:
        """Показ на доске (решение №53): педагог только показывает экран (и звук вкладки), никого не видит;
        доска только смотрит и сама невидима."""
        grants = api.VideoGrants(
            room_join=True, room=room, can_publish=presenter, can_subscribe=not presenter, can_publish_data=False,
            can_publish_sources=["screen_share", "screen_share_audio"] if presenter else [], hidden=not presenter,
            can_update_own_metadata=presenter,  # режим повышенного качества экрана — атрибут педагога
        )
        return (
            api.AccessToken(self.key, self.secret)
            .with_identity(identity)
            .with_name(name)
            .with_grants(grants)
            .with_ttl(ttl)
            .to_jwt()
        )

    async def start_track_recording(self, room: str, track_sid: str, filepath: str) -> str:
        """Запись одной дорожки (экран ученика) как есть, без перекодирования; S3 — из конфига egress.
        Путь — без расширения: egress сам добавит .webm (VP8) или .mp4 (H.264)."""
        async with self._api() as lk:
            try:
                info = await lk.egress.start_track_egress(api.TrackEgressRequest(
                    room_name=room, track_id=track_sid, file=api.DirectFileOutput(filepath=filepath),
                ))
            except api.TwirpError as e:
                raise LiveKitError(e.message) from e
            return info.egress_id

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
                    # Облегчённая запись для ВМ на 2 vCPU: 720p, 15 кадров/с (доска и презентации читаются,
                    # Chrome в egress не задыхается), битрейт ниже — файлы меньше.
                    advanced=api.EncodingOptions(width=1280, height=720, framerate=15, video_bitrate=1500, audio_bitrate=96),
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
            try:
                out.metadata = json.loads(event.participant.metadata) if event.participant.metadata else None
            except ValueError:
                out.metadata = None
        if event.HasField("track"):
            out.track_sid, out.track_source = event.track.sid, api.TrackSource.Name(event.track.source)
        if event.HasField("egress_info"):
            info = event.egress_info
            out.room = out.room or info.room_name
            out.egress_id, out.egress_status, out.egress_error = info.egress_id, api.EgressStatus.Name(info.status), info.error or None
            if info.file_results:
                f = info.file_results[0]
            elif info.HasField("file"):  # запись дорожки: итог — в устаревшем поле file
                f = info.file
            else:
                f = None
            if f is not None:
                out.file_size, out.file_name = int(f.size), f.filename or None
                out.file_duration_s = _duration_s(f.duration, info.started_at, info.ended_at)
        return out


def _duration_s(duration_ns: int, started_ns: int, ended_ns: int) -> int | None:
    """Длительность файла в секундах. У записи отдельной дорожки egress присылает в duration мусор
    (отрицательное число) — тогда считаем по времени начала и конца egress; не вышло — None."""
    for value in (duration_ns, ended_ns - started_ns if started_ns and ended_ns else 0):
        seconds = int(value // 1_000_000_000)
        if 0 < seconds < 24 * 3600:
            return seconds
    return None
