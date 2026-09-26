from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


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


class MemberOut(BaseModel):
    student_id: UUID
    full_name: str
    login: str | None
    joined_at: datetime


class GroupDetail(GroupOut):
    members: list[MemberOut]


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


class ManualStudentCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    login: str | None = Field(None, max_length=32)
    password: str | None = Field(None, min_length=6, max_length=128)
    group_id: UUID | None = None


class StudentCredentials(BaseModel):
    student: StudentOut
    login: str | None
    password: str | None


class StudentUpdate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)


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
