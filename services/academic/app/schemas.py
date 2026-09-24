from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

AttendanceStatus = Literal["present", "absent", "late", "sick"]


def _required_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Комментарий обязателен")
    return value


class GradeTypeOut(BaseModel):
    id: UUID
    name: str
    position: int
    is_active: bool


class GradeTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    position: int = 0

    _name = field_validator("name")(_required_text)


class GradeTypeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    position: int | None = None
    is_active: bool | None = None


class GradeCreate(BaseModel):
    student_id: UUID
    value: int = Field(ge=1, le=5)
    grade_type_id: UUID
    comment: str = Field(max_length=1000)

    _comment = field_validator("comment")(_required_text)


class GradeUpdate(BaseModel):
    value: int | None = Field(None, ge=1, le=5)
    grade_type_id: UUID | None = None
    comment: str | None = Field(None, max_length=1000)

    @field_validator("comment")
    @classmethod
    def _comment(cls, value: str | None) -> str | None:
        return None if value is None else _required_text(value)


class GradeOut(BaseModel):
    id: UUID
    lesson_id: UUID
    student_id: UUID
    value: int
    grade_type_id: UUID
    grade_type: str
    comment: str
    source: str
    lesson_starts_at: datetime
    created_at: datetime


class AttendanceSet(BaseModel):
    status: AttendanceStatus | None = Field(description="null — снять отметку")


class AttendanceOut(BaseModel):
    lesson_id: UUID
    student_id: UUID
    status: AttendanceStatus


class Stats(BaseModel):
    average: float | None = Field(description="Средний балл, null — оценок нет")
    grades_count: int
    present: int
    late: int
    absent: int
    sick: int
    attendance_rate: float | None = Field(description="Доля посещённых (присутствовал или опоздал) среди отмеченных")


class JournalLesson(BaseModel):
    id: UUID
    starts_at: datetime
    subject: str | None
    topic: str | None
    started: bool


class JournalStudent(BaseModel):
    id: UUID
    full_name: str
    current: bool = Field(description="Сейчас в группе (ушедшие показываются, если у них есть записи)")
    stats: Stats


class Journal(BaseModel):
    title: str
    lessons: list[JournalLesson]
    students: list[JournalStudent]
    grades: list[GradeOut]
    attendance: list[AttendanceOut]
    stats: Stats


class SubjectGrades(BaseModel):
    subject: str
    teacher_names: list[str]
    stats: Stats
    grades: list[GradeOut]


class MyGrades(BaseModel):
    subjects: list[SubjectGrades]
    stats: Stats
