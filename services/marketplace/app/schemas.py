from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

Level = Literal["1-4", "5-9", "10-11", "student", "adult"]
Format = Literal["individual", "group"]


def _clean(value: str) -> str:
    return " ".join(value.split())


class SubjectRef(BaseModel):
    id: UUID
    name: str


class ProfileIn(BaseModel):
    published: bool = False
    headline: str = Field("", max_length=150)
    about: str = Field("", max_length=5000)
    photo_file_id: UUID | None = None
    subject_ids: list[UUID] = Field(default_factory=list, max_length=10)
    levels: list[Level] = Field(default_factory=list)
    formats: list[Format] = Field(default_factory=list)
    price: int | None = Field(None, ge=100, le=100_000, description="Ориентир за 60 минут, ₽")
    experience_years: int | None = Field(None, ge=0, le=70)

    _headline = field_validator("headline")(_clean)


class Presence(BaseModel):
    online: bool
    last_seen_at: datetime | None


class TutorCard(BaseModel):
    user_id: UUID
    full_name: str
    photo_url: str | None
    headline: str
    subjects: list[SubjectRef]
    levels: list[str]
    formats: list[str]
    price: int | None
    experience_years: int | None
    rating: float | None
    reviews_count: int
    education_verified: bool
    presence: Presence


class EducationOut(BaseModel):
    id: UUID
    title: str
    institution: str
    year: int
    status: str | None = Field(None, description="Только владельцу и модератору")
    comment: str | None = None
    filename: str | None = None
    file_url: str | None = None


class TutorPublic(TutorCard):
    about: str
    published: bool
    share_url: str
    education: list[EducationOut] = Field(description="Одобренные документы — вошедшим пользователям; гостям — только бейдж")


class MyProfile(BaseModel):
    profile: TutorPublic
    photo_file_id: UUID | None
    missing: list[str] = Field(description="Чего не хватает, чтобы профиль появился в поиске")
    education: list[EducationOut]


class EducationIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    institution: str = Field(min_length=1, max_length=200)
    year: int = Field(ge=1950, le=2100)
    file_id: UUID

    _title = field_validator("title", "institution")(_clean)


class SearchPage(BaseModel):
    items: list[TutorCard]
    total: int
