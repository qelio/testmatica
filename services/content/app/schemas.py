from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


class SubjectOut(BaseModel):
    id: UUID
    name: str
    hidden: bool = False


class SubjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class SubjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    hidden: bool | None = None
    position: int | None = Field(None, ge=0)


# Оформление курса для учеников (решение №42). Новая тема — сюда, в web/src/lib/course-themes.ts и в mcp.
Theme = Literal["classic", "comics", "code"]


class CourseSummary(BaseModel):
    id: UUID
    title: str
    description: str
    subject: SubjectOut | None
    owner_id: UUID
    author_name: str
    status: str
    review_comment: str | None
    theme: str
    sections_count: int
    materials_count: int
    updated_at: datetime


class MaterialBrief(BaseModel):
    id: UUID
    kind: str
    title: str
    viewed: bool
    favorite: bool


class ModuleOut(BaseModel):
    id: UUID
    title: str
    description: str
    materials: list[MaterialBrief]
    origin_id: UUID | None = Field(None, description="В черновике изменений — модуль опубликованной версии (решение №46)")


class SectionOut(BaseModel):
    id: UUID
    title: str
    description: str
    modules: list[ModuleOut]


class RevisionRef(BaseModel):
    """Черновик изменений опубликованного курса (решение №46) — автору и модераторам."""

    id: UUID
    status: str
    review_comment: str | None


class CourseOut(CourseSummary):
    sections: list[SectionOut]
    can_edit: bool
    viewed_count: int
    revision_of: UUID | None = Field(None, description="Это черновик изменений курса с этим id")
    revision: RevisionRef | None = Field(None, description="У опубликованного курса — его черновик изменений, если есть")


class FileInfo(BaseModel):
    id: UUID
    filename: str
    mime: str
    size: int | None
    url: str | None


class MaterialOut(BaseModel):
    id: UUID
    module_id: UUID
    course_id: UUID
    kind: str
    title: str
    body: str
    url: str | None
    file: FileInfo | None
    task_id: UUID | None
    position_sec: int
    viewed: bool
    favorite: bool


class ModuleContent(BaseModel):
    id: UUID
    title: str
    description: str
    course_id: UUID
    course_title: str
    course_theme: str
    section_title: str
    origin_id: UUID | None = Field(None, description="В черновике изменений — модуль опубликованной версии")
    revision_of: UUID | None = Field(None, description="Модуль черновика изменений курса с этим id")
    materials: list[MaterialOut]
    prev_module_id: UUID | None
    next_module_id: UUID | None
    can_edit: bool


# ---------- редактирование ----------


class CourseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    subject_id: UUID | None = None
    description: str = Field("", max_length=5000)
    theme: Theme = "classic"

    _title = field_validator("title")(_clean)


class NodeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=5000)

    _title = field_validator("title")(_clean)


class NodeUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    subject_id: UUID | None = None
    theme: Theme | None = Field(None, description="Только у курса")

    _title = field_validator("title")(_clean)


class MaterialCreate(BaseModel):
    kind: Literal["text", "card", "video", "pdf", "file", "link", "task"]
    title: str | None = Field(None, max_length=200, description="Для задачи — по умолчанию её название")
    body: str = Field("", max_length=200_000)
    file_id: UUID | None = None
    url: str | None = Field(None, max_length=500)
    task_id: UUID | None = None

    _title = field_validator("title")(_clean)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        value = (value or "").strip() or None
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("Ссылка должна начинаться с https://")
        return value

    @model_validator(mode="after")
    def _fields_by_kind(self) -> "MaterialCreate":
        if self.kind in ("video", "pdf", "file") and self.file_id is None:
            raise ValueError("Загрузите файл")
        if self.kind == "link" and not self.url:
            raise ValueError("Укажите ссылку")
        if self.kind in ("text", "card") and not self.body.strip():
            raise ValueError("Напишите текст")
        if self.kind == "task" and self.task_id is None:
            raise ValueError("Выберите задачу из банка")
        if self.kind != "task" and not self.title:
            raise ValueError("Укажите название")
        return self


class MaterialUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    body: str | None = Field(None, max_length=200_000)
    url: str | None = Field(None, max_length=500)

    _title = field_validator("title")(_clean)


class Move(BaseModel):
    direction: Literal["up", "down"]


class ProgressUpdate(BaseModel):
    position_sec: int | None = Field(None, ge=0)


class ProgressReport(BaseModel):
    materials: list[dict]
    students: list[dict]
