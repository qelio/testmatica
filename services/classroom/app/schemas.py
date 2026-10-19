from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator
from testmatica_common.names import PersonName


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


class GroupCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    kind: Literal["class", "group"] = "group"
    paid: bool = False
    subject: str | None = Field(None, max_length=80)
    description: str = Field("", max_length=2000)

    _title = field_validator("title", "subject")(_clean)


class GroupUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=120)
    subject: str | None = Field(None, max_length=80)
    description: str | None = Field(None, max_length=2000)
    paid: bool | None = None

    _title = field_validator("title", "subject")(_clean)


class GroupOut(BaseModel):
    id: UUID
    kind: str
    paid: bool
    title: str
    subject: str | None
    description: str
    archived: bool
    student_count: int
    created_at: datetime
    shared: bool = Field(False, description="Класс коллеги, которым он поделился (решение №57): только свои занятия и тесты")
    owner_name: str | None = Field(None, description="Чей класс — у класса коллеги")


class ShareOut(BaseModel):
    user_id: UUID
    full_name: str


class ShareIn(BaseModel):
    colleague_id: UUID


class MemberOut(BaseModel):
    student_id: UUID
    full_name: str
    login: str | None
    joined_at: datetime


class GroupDetail(GroupOut):
    members: list[MemberOut]
    shares: list[ShareOut] = Field(default_factory=list, description="Владельцу — с какими коллегами поделился")


class StudentOut(BaseModel):
    student_id: UUID
    full_name: str
    login: str | None
    status: str
    source: str
    managed: bool = Field(description="Аккаунт создан педагогом — можно менять имя и пароль")
    group_ids: list[UUID]
    paid: bool = Field(description="Индивидуальные занятия платные")
    price: int | None = Field(None, description="Цена занятия по договорённости в маркетплейсе, ₽")
    lesson_minutes: int | None = None


class ManualStudentCreate(PersonName):
    login: str | None = Field(None, max_length=32)
    password: str | None = Field(None, min_length=6, max_length=128)
    group_id: UUID | None = None


class StudentCredentials(BaseModel):
    student: StudentOut
    login: str | None
    password: str | None


class BulkStudentsCreate(BaseModel):
    full_names: list[str] = Field(min_length=1, max_length=40,
                                  description="По одному ученику: «Фамилия Имя Отчество»; логин и пароль — автоматически")
    group_id: UUID | None = None

    @field_validator("full_names")
    @classmethod
    def _names(cls, v: list[str]) -> list[str]:
        names = [" ".join(n.split()) for n in v]
        names = [n for n in names if n]
        if not names:
            raise ValueError("Укажите хотя бы одного ученика")
        if any(len(n) > 200 for n in names):
            raise ValueError("Слишком длинное имя")
        return names


class BulkError(BaseModel):
    full_name: str
    message: str


class BulkStudentsOut(BaseModel):
    created: list[StudentCredentials]
    errors: list[BulkError]


class CardIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class CardsIn(BaseModel):
    students: list[CardIn] = Field(min_length=1, max_length=60)
    title: str | None = Field(None, max_length=120, description="Подпись на листе: например, класс")


class SignedOut(BaseModel):
    count: int = Field(description="Скольких учеников вывели из аккаунта")


class StudentUpdate(BaseModel):
    name: PersonName


class StudentBilling(BaseModel):
    paid: bool


class LinkRequestCreate(BaseModel):
    identifier: str = Field(min_length=1, max_length=254, description="Логин или email ученика")
    group_id: UUID | None = None


class AddMember(BaseModel):
    student_id: UUID


class InvitationCreate(BaseModel):
    email: EmailStr
    group_id: UUID | None = None


class InvitationOut(BaseModel):
    id: UUID
    email: str
    group_id: UUID | None
    expires_at: datetime
    created_at: datetime


class InvitationPublic(BaseModel):
    status: Literal["valid", "expired", "used", "revoked"]
    teacher_name: str
    group_title: str | None
    group_kind: str | None


class TeacherGroupRef(BaseModel):
    id: UUID
    title: str


class MyTeacherOut(BaseModel):
    link_id: UUID
    teacher_id: UUID
    full_name: str
    status: str
    groups: list[TeacherGroupRef]


class MyGroupOut(BaseModel):
    id: UUID
    title: str
    subject: str | None
    kind: str
    teacher_id: UUID
    teacher_name: str


class ColleagueRequestIn(BaseModel):
    identifier: str = Field(min_length=1, max_length=254, description="Логин или почта педагога")


class ColleagueOut(BaseModel):
    user_id: UUID
    full_name: str
    login: str | None
    since: datetime


class ColleagueRequestOut(BaseModel):
    id: UUID
    user_id: UUID = Field(description="Кто прислал (входящая) или кому отправлена (исходящая)")
    full_name: str
    login: str | None
    created_at: datetime


class ColleaguesOut(BaseModel):
    colleagues: list[ColleagueOut]
    incoming: list[ColleagueRequestOut]
    outgoing: list[ColleagueRequestOut]
