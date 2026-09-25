from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RoomOut(BaseModel):
    lesson_id: UUID
    title: str
    is_teacher: bool
    status: Literal["waiting", "active", "ended"]
    started_at: datetime | None
    lesson_ends_at: datetime
    limit_ends_at: datetime | None = Field(description="Когда бесплатное занятие завершится автоматически")
    end_reason: str | None
    screen_share: list[UUID] = Field(description="Ученики, которым разрешено показывать экран")
    recording: Literal["starting", "active", "stopping"] | None = Field(
        description="Запись: запускается (несколько секунд), идёт, сохраняется после остановки"
    )
    max_participants: int
    external_url: str | None = Field(description="Ссылка на внешний сервис, если педагог выбрал его")


class JoinOut(BaseModel):
    url: str = Field(description="Адрес LiveKit для браузера")
    token: str
    room: RoomOut


class ScreenShareIn(BaseModel):
    student_id: UUID
    allowed: bool


class RecordingOut(BaseModel):
    id: UUID
    lesson_id: UUID
    title: str
    status: str
    error: str | None = Field(None, description="Почему запись не сохранилась — педагогу")
    started_at: datetime
    ended_at: datetime | None
    duration_s: int | None
    size: int | None
    expires_at: datetime | None
    url: str | None = Field(None, description="Просмотр")
    download_url: str | None = None
    can_delete: bool
