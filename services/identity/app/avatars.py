"""Фото профиля — одно на пользователя: в кабинете, шапке и анкете репетитора."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .deps import media, outbox
from .models import User


async def set_avatar(session: AsyncSession, user: User, file_id: UUID | None) -> None:
    """Закрепить файл за identity и сообщить сервисам. Коммит — за вызывающим."""
    if file_id == user.avatar_file_id:
        return
    if file_id:
        await media.post("/internal/files/claim", json={
            "owner_id": str(user.id), "purpose": "avatar", "file_ids": [str(file_id)], "claimed_by": "identity"})
    user.avatar_file_id = file_id
    await outbox.event(session, "identity.user.avatar_changed",
                       {"user_id": str(user.id), "file_id": str(file_id) if file_id else None}, actor_id=user.id)
