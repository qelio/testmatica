from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

Scope = Literal["this", "following"]


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


def _url(value: str | None) -> str | None:
    value = _clean(value)
    if value and not value.startswith(("https://", "http://")):
        raise ValueError("Ссылка должна начинаться с https://")
    return value


class Repeat(BaseModel):
    weekdays: list[int] = Field(default_factory=list, description="0 — пн … 6 — вс; пусто — день первого занятия")
    interval_weeks: int = Field(1, ge=1, le=8)
    until: date | None = None
    count: int | None = Field(None, ge=1, le=200)

    @field_validator("weekdays")
    @classmethod
    def _weekdays(cls, value: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in value):
            raise ValueError("Дни недели — числа от 0 до 6")
        return sorted(set(value))

    @model_validator(mode="after")
    def _bounded(self) -> "Repeat":
        if self.until is None and self.count is None:
            raise ValueError("Укажите дату окончания или количество занятий")
        return self


class LessonCreate(BaseModel):
    kind: Literal["individual", "group"]
    group_id: UUID | None = None
    student_id: UUID | None = None
    starts_at: datetime
    duration_min: int = Field(ge=15, le=300)
    subject: str | None = Field(None, max_length=80)
    topic: str | None = Field(None, max_length=300)
    exam_item_ids: list[UUID] | None = Field(None, max_length=10, description="Задания ЕГЭ/ОГЭ на занятии")
    paid: bool | None = Field(None, description="Платное ли занятие; по умолчанию — как у группы или ученика")
    trial: bool = Field(False, description="Пробное занятие — после него ученику придёт опрос: отзыв и продолжать ли")
    video_url: str | None = Field(None, max_length=500)
    repeat: Repeat | None = None
    timezone: str = Field("Europe/Moscow", max_length=64)

    _subject = field_validator("subject", "topic")(_clean)
    _video = field_validator("video_url")(_url)

    @field_validator("starts_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Время нужно передавать с часовым поясом (ISO 8601)")
        return value

    @model_validator(mode="after")
    def _target(self) -> "LessonCreate":
        if self.kind == "group" and self.group_id is None:
            raise ValueError("Выберите группу")
        if self.kind == "individual" and self.student_id is None:
            raise ValueError("Выберите ученика")
        return self


class LessonUpdate(BaseModel):
    scope: Scope = "this"
    starts_at: datetime | None = None
    duration_min: int | None = Field(None, ge=15, le=300)
    subject: str | None = Field(None, max_length=80)
    topic: str | None = Field(None, max_length=300)
    exam_item_ids: list[UUID] | None = Field(None, max_length=10, description="Задания ЕГЭ/ОГЭ на занятии")
    paid: bool | None = None
    trial: bool | None = None
    video_url: str | None = Field(None, max_length=500)

    _subject = field_validator("subject", "topic")(_clean)
    _video = field_validator("video_url")(_url)


class CancelRequest(BaseModel):
    scope: Scope = "this"
    reason: str | None = Field(None, max_length=500)


class RescheduleCreate(BaseModel):
    starts_at: datetime
    comment: str | None = Field(None, max_length=500)


class Person(BaseModel):
    id: UUID
    full_name: str


class RescheduleOut(BaseModel):
    id: UUID
    lesson_id: UUID
    requested_by: UUID
    requested_by_me: bool
    new_starts_at: datetime
    new_ends_at: datetime
    comment: str | None
    status: str
    created_at: datetime


class LessonOut(BaseModel):
    id: UUID
    series_id: UUID | None
    teacher: Person
    paid: bool
    trial: bool
    kind: str
    group_id: UUID | None
    title: str = Field(description="Название группы или имя ученика")
    subject: str | None
    topic: str | None
    exam_item_ids: list[UUID]
    starts_at: datetime
    ends_at: datetime
    duration_min: int
    status: str
    video_url: str | None
    cancel_reason: str | None
    participants: list[Person] | None = Field(description="Только для педагога")
    pending_reschedule: RescheduleOut | None


class RescheduleWithLesson(RescheduleOut):
    lesson: LessonOut


class CreatedLessons(BaseModel):
    count: int
    lessons: list[LessonOut]
