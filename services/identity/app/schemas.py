import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

CONSENT_PDN_VERSION = "1.0"


def _check_password(value: str) -> str:
    if not re.search(r"[A-Za-zА-Яа-яЁё]", value) or not re.search(r"\d", value):
        raise ValueError("Пароль должен содержать буквы и цифры")
    return value


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    role: Literal["student", "teacher"]
    consent_pdn: bool
    consent_version: str = CONSENT_PDN_VERSION

    _password = field_validator("password")(_check_password)

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Укажите имя")
        return value

    @field_validator("consent_pdn")
    @classmethod
    def _consent_required(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Необходимо согласие на обработку персональных данных")
        return value


class RegisterResponse(BaseModel):
    user_id: UUID
    challenge_id: UUID
    destination: str


class CodeRequest(BaseModel):
    challenge_id: UUID
    code: str = Field(pattern=r"^\d{6}$")


class ResendRequest(BaseModel):
    challenge_id: UUID


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=254, description="Email или логин")
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: UUID
    email: str | None
    login: str | None
    full_name: str
    roles: list[str]
    teacher_mode: str | None
    two_factor_method: str | None
    timezone: str

    @classmethod
    def of(cls, user) -> "UserOut":
        return cls(
            id=user.id,
            email=user.email,
            login=user.login,
            full_name=user.full_name,
            roles=user.role_names,
            teacher_mode=user.teacher_mode,
            two_factor_method=user.two_factor_method,
            timezone=user.timezone,
        )


class TwoFactorRequired(BaseModel):
    status: Literal["2fa_required"] = "2fa_required"
    challenge_id: UUID
    method: str
    destination: str


class Authenticated(BaseModel):
    status: Literal["authenticated"] = "authenticated"
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ChallengeResponse(BaseModel):
    challenge_id: UUID


class ResetPasswordRequest(CodeRequest):
    new_password: str = Field(min_length=8, max_length=128)

    _password = field_validator("new_password")(_check_password)


class TeacherModeRequest(BaseModel):
    mode: Literal["school", "tutor"]
