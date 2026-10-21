from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

Access = Literal["none", "read", "edit"]
PaperStyle = Literal["plain", "lines_narrow", "lines", "lines_wide", "grid_small", "grid", "grid_big", "dots"]
PaperColor = Literal["white", "cream", "yellow", "blue", "green", "pink", "gray", "chalk"]
Role = Literal["owner", "edit", "read"]


def _title(v: str | None) -> str | None:
    return " ".join(v.split()) if v is not None else None


class BoardCreate(BaseModel):
    """Свободная доска; по желанию — видна классу или ученику."""

    title: str = Field(min_length=1, max_length=200)
    group_id: UUID | None = None
    student_id: UUID | None = None
    access: Access = "read"

    _clean = field_validator("title")(_title)


class BoardUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    access: Access | None = None
    paper_style: PaperStyle | None = None
    paper_color: PaperColor | None = None
    # Кому видна свободная доска: передайте оба поля (null и null — никому).
    target: dict[str, UUID | None] | None = Field(None, description='{"group_id": …} или {"student_id": …} или {}')

    _clean = field_validator("title")(_title)


class BoardSummary(BaseModel):
    id: UUID
    title: str
    owner_id: UUID
    owner_name: str
    lesson_id: UUID | None
    lesson_starts_at: datetime | None
    group_id: UUID | None
    student_id: UUID | None
    target_title: str | None
    access: Access
    paper_style: PaperStyle
    paper_color: PaperColor
    role: Role
    items_count: int = 0
    updated_at: datetime


class ItemIn(BaseModel):
    id: UUID
    kind: Literal["stroke", "shape", "text", "image", "formula"]
    data: dict[str, Any]
    z: float = 0


class ItemOut(ItemIn):
    author_id: UUID


class BoardOut(BoardSummary):
    items: list[ItemOut]


class Ops(BaseModel):
    """Правка доски: добавить или изменить объекты и удалить объекты."""

    upsert: list[ItemIn] = Field(default_factory=list)
    delete: list[UUID] = Field(default_factory=list)
