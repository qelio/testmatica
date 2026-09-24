from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from .config import settings


class MessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=settings.message_max_length)
    announcement: bool = Field(False, description="Объявление в групповом чате (только педагог) — закрепляется")

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Пустое сообщение")
        return value


class MessageOut(BaseModel):
    id: UUID
    conversation_id: UUID
    author_id: UUID
    author_name: str
    text: str
    is_announcement: bool
    deleted: bool
    created_at: datetime


class ConversationOut(BaseModel):
    id: UUID
    kind: str
    title: str
    group_id: UUID | None
    other_user_id: UUID | None = Field(description="Собеседник в личном диалоге")
    my_role: str
    can_write: bool
    unread: int
    last_message: MessageOut | None
    pinned: MessageOut | None
    last_message_at: datetime | None


class DirectCreate(BaseModel):
    user_id: UUID


class ReadMark(BaseModel):
    at: datetime | None = Field(None, description="До какого момента прочитано; по умолчанию — сейчас")


class Contact(BaseModel):
    id: UUID
    full_name: str
    relation: str
