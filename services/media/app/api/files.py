import io
import mimetypes
from datetime import UTC, datetime
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal
from testmatica_common.errors import ApiError
from testmatica_common.ids import uuid7

from .. import importer, storage
from ..deps import auth, db, outbox
from ..models import StoredFile
from ..policy import MB, PURPOSES, extension, safe_filename
from ..schemas import FileOut

router = APIRouter(prefix="/files", tags=["files"])


def file_out(f: StoredFile, url: str | None = None) -> FileOut:
    return FileOut(
        id=f.id, filename=f.filename, mime=f.mime, size=f.size, purpose=f.purpose, created_at=f.created_at, url=url
    )


@router.post("", response_model=FileOut, status_code=201)
async def upload(
    file: UploadFile = File(...),
    purpose: str = Form(...),
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> FileOut:
    """Загрузить файл. Возвращает id — его передают в сообщение, ответ на задание и т. п."""
    rule = PURPOSES.get(purpose)
    if rule is None:
        raise ApiError(422, "invalid_purpose", "Неизвестное назначение файла")
    filename = safe_filename(file.filename or "file")
    ext = extension(filename)
    if ext not in rule.extensions:
        raise ApiError(
            422, "file_type_not_allowed", f"Такой тип файла нельзя загрузить как {rule.label}", {"extension": ext}
        )
    size = file.size or 0
    if size == 0:
        raise ApiError(422, "empty_file", "Файл пустой")
    if size > rule.max_size:
        raise ApiError(
            413, "file_too_large", f"Файл больше {rule.max_size // MB} МБ", {"max_size": rule.max_size}
        )

    # Тип определяем по расширению, а не по заголовку от клиента.
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    stored = await _store(session, principal, purpose, filename, ext, mime, size, file.file)
    return file_out(stored)


class ImportIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


@router.post("/import", response_model=FileOut, status_code=201)
async def import_image(body: ImportIn, principal: Principal = Depends(auth.principal),
                       session: AsyncSession = Depends(db.session)) -> FileOut:
    """Перенести картинку с другого сайта (вставили текст вместе с картинкой): скачиваем сами и храним как «content».
    Иначе картинка ссылалась бы на чужой сайт — а он часто не отдаёт картинки другим сайтам или удаляет их."""
    data, ext, mime = await importer.fetch_image(body.url)
    name = safe_filename(PurePosixPath(urlsplit(body.url).path).stem or "картинка") + ext
    return file_out(await _store(session, principal, "content", name, ext, mime, len(data), io.BytesIO(data)))


async def _store(session: AsyncSession, principal: Principal, purpose: str, filename: str, ext: str, mime: str,
                 size: int, body) -> StoredFile:
    file_id = uuid7()
    now = datetime.now(UTC)
    key = f"{purpose}/{now:%Y/%m}/{file_id}{ext}"
    await storage.put(key, body, mime)

    stored = StoredFile(
        id=file_id, owner_id=principal.user_id, purpose=purpose, filename=filename, mime=mime, size=size, key=key
    )
    session.add(stored)
    await session.flush()
    await outbox.event(
        session,
        "media.file.uploaded",
        {"file_id": str(file_id), "purpose": purpose, "size": size, "mime": mime},
        actor_id=principal.user_id,
    )
    await session.commit()
    return stored


async def _own(session: AsyncSession, file_id: UUID, principal: Principal) -> StoredFile:
    stored = await session.get(StoredFile, file_id)
    if stored is None or stored.owner_id != principal.user_id or stored.status != "ready":
        raise ApiError(404, "file_not_found", "Файл не найден")
    return stored


@router.get("/{file_id}/content", response_class=RedirectResponse, status_code=302)
async def content(file_id: UUID, session: AsyncSession = Depends(db.session)) -> RedirectResponse:
    """Постоянная ссылка на картинку или файл внутри текста: каждый раз — свежая временная ссылка в хранилище.
    Без входа — тексты бывают публичными (библиотека, новости). Только файлы с назначением «content»;
    отдаются с домена хранилища, так что HTML внутри файла не выполнится на нашем сайте."""
    stored = await session.get(StoredFile, file_id)
    if stored is None or stored.purpose != "content" or stored.status != "ready":
        raise ApiError(404, "file_not_found", "Файл не найден")
    url = await storage.presigned_url(stored.key, stored.filename, stored.mime)
    # Браузер может переиспользовать переадресацию несколько минут — временная ссылка живёт дольше.
    return RedirectResponse(url, status_code=302, headers={"Cache-Control": "private, max-age=300"})


@router.get("/{file_id}", response_model=FileOut)
async def get_own(
    file_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> FileOut:
    """Свой файл (например, только что загруженный). Чужие файлы выдаёт сервис, к которому они прикреплены."""
    stored = await _own(session, file_id, principal)
    return file_out(stored, await storage.presigned_url(stored.key, stored.filename, stored.mime))


@router.delete("/{file_id}", status_code=204)
async def delete_own(
    file_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> None:
    """Удалить свой ещё не использованный файл (например, передумал прикреплять)."""
    stored = await _own(session, file_id, principal)
    if stored.claimed_by is not None:
        raise ApiError(409, "file_in_use", "Файл уже прикреплён и не может быть удалён")
    stored.status = "deleted"
    await session.commit()
    await storage.delete(stored.key)
