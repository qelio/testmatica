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


# ---------- прокторинг ----------


class ProctorStudentOut(BaseModel):
    id: UUID
    full_name: str
    attempt_id: UUID | None


class ProctorJoinOut(BaseModel):
    url: str
    token: str
    role: str = Field(description="teacher — смотрит экраны; student — показывает свой")
    title: str
    students: list[ProctorStudentOut] = Field(default_factory=list, description="Педагогу — ученики назначения")


class ProctorRecordingOut(BaseModel):
    id: UUID
    student_id: UUID
    student_name: str
    attempt_id: UUID | None
    status: str
    started_at: datetime
    duration_s: int | None
    url: str | None
    download_url: str | None
    expires_at: datetime | None


class BoardCreated(BaseModel):
    """Новая доска: код показывается на экране, secret хранит только сама доска."""

    id: UUID
    code: str
    secret: str
    expires_at: datetime


class BoardStatus(BaseModel):
    status: str = Field(description="waiting — ждёт педагога; live — педагог подключился; ended — показ завершён; expired — код истёк")
    code: str
    expires_at: datetime
    teacher_name: str | None = None
    url: str | None = Field(None, description="Адрес LiveKit — когда live")
    token: str | None = Field(None, description="Пропуск доски (только смотреть) — когда live")


class BoardPairIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class BoardPairOut(BaseModel):
    id: UUID
    url: str
    token: str = Field(description="Пропуск педагога: только показ экрана (со звуком вкладки)")
