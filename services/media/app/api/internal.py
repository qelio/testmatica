"""Внутренние эндпоинты: прикрепление файлов к сущностям других сервисов и выдача ссылок."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError
from testmatica_common.internal import internal_guard

from .. import storage
from ..config import settings
from ..deps import db
from ..models import StoredFile
from ..schemas import ClaimRequest, FileOut, UrlsRequest
from .files import file_out

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(internal_guard(settings.internal_token))])


@router.post("/files/claim", response_model=list[FileOut])
async def claim(body: ClaimRequest, session: AsyncSession = Depends(db.session)) -> list[FileOut]:
    """Проверить, что файлы принадлежат пользователю и загружены для этой цели, и закрепить их за сервисом.
    Так нельзя прикрепить к своему сообщению чужой файл, подсмотрев его id."""
    if not body.file_ids:
        return []
    ids = list(dict.fromkeys(body.file_ids))
    rows = {
        f.id: f
        for f in (await session.execute(select(StoredFile).where(StoredFile.id.in_(ids)).with_for_update())).scalars()
    }
    for fid in ids:
        f = rows.get(fid)
        if f is None or f.owner_id != body.owner_id or f.status != "ready" or f.purpose != body.purpose:
            raise ApiError(422, "invalid_attachment", "Файл не найден или загружен для другой цели", {"file_id": str(fid)})
        if f.claimed_by not in (None, body.claimed_by):
            raise ApiError(409, "file_in_use", "Файл уже используется", {"file_id": str(fid)})
    now = datetime.now(UTC)
    for f in rows.values():
        f.claimed_by = body.claimed_by
        f.claimed_at = f.claimed_at or now
    await session.commit()
    return [file_out(rows[fid]) for fid in ids]


@router.post("/files/urls", response_model=dict[str, FileOut])
async def urls(body: UrlsRequest, session: AsyncSession = Depends(db.session)) -> dict[str, FileOut]:
    """Ссылки на скачивание. Вызывает сервис-владелец сущности после своей проверки доступа."""
    if not body.file_ids:
        return {}
    rows = (
        await session.execute(
            select(StoredFile).where(StoredFile.id.in_(body.file_ids), StoredFile.status == "ready")
        )
    ).scalars()
    return {str(f.id): file_out(f, await storage.presigned_url(f.key, f.filename, f.mime)) for f in rows}
