import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from .config import settings
from .legal import CURRENT, PDN, TERMS


def _check_password(value: str) -> str:
    if not re.search(r"[A-Za-zА-Яа-яЁё]", value) or not re.search(r"\d", value):
        raise ValueError("Пароль должен содержать буквы и цифры")
    return value


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    role: Literal["student", "teacher"]
    consent_pdn: bool = Field(description="Согласие на обработку персональных данных — отдельной галочкой (152-ФЗ)")
    accept_terms: bool = Field(description="Принимаю пользовательское соглашение")

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

    @field_validator("accept_terms")
    @classmethod
    def _terms_required(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Необходимо принять пользовательское соглашение")
        return value


class ConsentsIn(BaseModel):
    """Окно согласия при входе: ученик, созданный педагогом, или новая редакция документов."""

    accept_terms: bool
    consent_pdn: bool
    by_representative: bool = Field(False, description="Согласие даёт родитель (законный представитель) ученика младше 14 лет")

    @field_validator("accept_terms", "consent_pdn")
    @classmethod
    def _required(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Без согласия пользоваться платформой нельзя")
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
    two_factor_method: str | None
    timezone: str
    email_verified: bool = False
    managed: bool = Field(False, description="Аккаунт создал педагог — логин и пароль он же и выдаёт")
    two_factor_required: bool = Field(False, description="2FA нельзя выключить (модераторы и администраторы)")
    avatar_url: str | None = None
    consent_required: bool = Field(False, description="Нужно принять соглашение и дать согласие на обработку ПД (текущие редакции)")
    email_codes: bool = Field(True, description="Письма с кодами работают; false — вход с кодом, смена email и сброс пароля «скоро»")

    @classmethod
    def of(cls, user, avatar_url: str | None = None, consent_required: bool = False) -> "UserOut":
        return cls(
            id=user.id,
            email=user.email,
            login=user.login,
            full_name=user.full_name,
            roles=user.role_names,
            two_factor_method=user.two_factor_method,
            timezone=user.timezone,
            email_verified=user.email_verified_at is not None,
            managed=user.managed_by_teacher_id is not None,
            two_factor_required=bool({"moderator", "admin"} & set(user.role_names)),
            avatar_url=avatar_url,
            consent_required=consent_required,
            email_codes=settings.email_codes,
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



