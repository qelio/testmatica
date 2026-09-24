from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FileOut(BaseModel):
    id: UUID
    filename: str
    mime: str
    size: int
    purpose: str
    created_at: datetime
    url: str | None = Field(None, description="Ссылка на скачивание (временная)")


class ClaimRequest(BaseModel):
    owner_id: UUID
    purpose: str
    file_ids: list[UUID] = Field(max_length=20)
    claimed_by: str = Field(max_length=32)


class UrlsRequest(BaseModel):
    file_ids: list[UUID] = Field(max_length=200)
