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


# ---------- заявки ----------

Goal = Literal["ege", "oge", "school", "gaps", "olympiad", "other"]


class ScheduleIn(BaseModel):
    """Удобные дни недели; время ученик и репетитор согласуют в чате."""

    weekdays: list[int] = Field(default_factory=list, max_length=7)

    @field_validator("weekdays")
    @classmethod
    def _days(cls, value: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in value):
            raise ValueError("День недели — от 0 (пн) до 6 (вс)")
        return sorted(set(value))


class RequestIn(BaseModel):
    tutor_id: UUID | None = Field(None, description="Кому адресована; без него — открытая заявка")
    subject_id: UUID
    goal: Goal
    current_ids: list[UUID] = Field(default_factory=list, max_length=30)
    desired_ids: list[UUID] = Field(default_factory=list, max_length=30)
    schedule: ScheduleIn = Field(default_factory=ScheduleIn)
    price: int = Field(ge=100, le=100_000, description="Предлагаемая цена за занятие, ₽")
    duration_min: Literal[30, 45, 60, 90] = 60
    comment: str = Field("", max_length=2000)


class CompetencyOut(BaseModel):
    id: UUID
    subject_id: UUID
    title: str
    position: int


class CompetencyIn(BaseModel):
    subject_id: UUID
    title: str = Field(min_length=1, max_length=120)

    _title = field_validator("title")(_clean)


class CompetencyUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=120)
    position: int | None = Field(None, ge=0)


class PersonBrief(BaseModel):
    id: UUID
    full_name: str
    photo_url: str | None = None
    rating: float | None = None
    reviews_count: int = 0


class ResponseOut(BaseModel):
    id: UUID = Field(description="Он же id чата переговоров")
    request_id: UUID
    tutor: PersonBrief
    status: str
    price: int
    proposed_by: Literal["student", "tutor"]
    message: str
    agreed_at: datetime | None
    created_at: datetime


class RequestOut(BaseModel):
    id: UUID
    student: PersonBrief
    tutor_id: UUID | None
    direct: bool
    subject_id: UUID
    subject_name: str
    goal: str
    current: list[str]
    desired: list[str]
    schedule: dict
    price: int
    duration_min: int
    comment: str
    status: str
    expires_at: datetime
    closed_at: datetime | None
    created_at: datetime
    responses: list[ResponseOut] = Field(default_factory=list, description="Ученику — все отклики; репетитору — только свой")


class Negotiation(BaseModel):
    """Переговоры глазами участника — для панели «Договорились» в чате."""

    response: ResponseOut
    request: RequestOut
    role: Literal["student", "tutor"]
    can_agree: bool = Field(description="Можно принять цену: её предложила другая сторона")


class PriceIn(BaseModel):
    price: int = Field(ge=100, le=100_000)


class RespondIn(BaseModel):
    price: int | None = Field(None, ge=100, le=100_000, description="Своя цена; по умолчанию — цена ученика")
    message: str = Field("", max_length=2000)


# ---------- отзывы ----------


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=10)
    text: str = Field(min_length=10, max_length=3000)

    @field_validator("text")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Напишите хотя бы пару предложений")
        return v


class ReplyIn(BaseModel):
    text: str = Field("", max_length=2000, description="Пустой текст — убрать ответ")


class DisputeIn(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


class RemoveIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class ReviewPublic(BaseModel):
    id: UUID
    student_name: str
    rating: int
    text: str
    published_at: datetime
    reply: str | None = Field(None, description="Ответ педагога — после одобрения модератором")


class MyReview(BaseModel):
    """Отзыв глазами автора-ученика."""

    id: UUID
    tutor_id: UUID
    tutor_name: str
    rating: int
    text: str
    status: str
    comment: str | None
    reply: str | None
    updated_at: datetime


class TutorReview(ReviewPublic):
    """Отзыв о себе глазами педагога: состояние ответа и спора."""

    reply_text: str | None
    reply_status: str | None
    reply_comment: str | None
    dispute_id: UUID | None
    dispute_status: str | None
    dispute_comment: str | None


class ReviewsPage(BaseModel):
    items: list[ReviewPublic]
    total: int
    rating: float | None
    reviews_count: int
    distribution: dict[int, int] = Field(description="Сколько отзывов с каждой оценкой 1–10")
    can_review: bool = Field(description="Текущий пользователь — ученик этого педагога и может оставить отзыв")
    mine: MyReview | None
