from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from .config import settings


class MessageCreate(BaseModel):
    text: str = Field("", max_length=settings.message_max_length)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=settings.max_attachments)
    announcement: bool = Field(False, description="Объявление в групповом чате (только педагог) — закрепляется")

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _not_empty(self) -> "MessageCreate":
        if not self.text and not self.attachment_ids:
            raise ValueError("Пустое сообщение")
        return self


class Attachment(BaseModel):
    id: UUID
    filename: str
    mime: str
    size: int
    url: str | None = Field(None, description="Временная ссылка на скачивание")


class MessageOut(BaseModel):
    id: UUID
    conversation_id: UUID
    author_id: UUID
    author_name: str
    text: str
    attachments: list[Attachment]
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
