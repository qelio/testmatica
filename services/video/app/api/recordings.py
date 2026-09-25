"""Записи занятий: смотреть и скачивать могут педагог и ученики занятия (ТЗ, раздел 7)."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal
from testmatica_common.errors import ApiError

from .. import rooms, storage
from ..deps import auth, db
from ..models import FAILED, READY, RECORDING, Recording
from ..schemas import RecordingOut

router = APIRouter(prefix="/recordings", tags=["recordings"])


async def _out(rec: Recording, p: Principal) -> RecordingOut:
    out = RecordingOut(
        id=rec.id, lesson_id=rec.lesson_id, title=rec.title, status=rec.status, started_at=rec.started_at,
        ended_at=rec.ended_at, duration_s=rec.duration_s, size=rec.size, expires_at=rec.expires_at,
        can_delete=rec.teacher_id == p.user_id, error=rec.error if rec.teacher_id == p.user_id else None,
    )
    if rec.status == READY:
        name = f"{rec.title}.mp4".replace("/", "-")
        out.url = await storage.url(rec.key, name, download=False)
        out.download_url = await storage.url(rec.key, name, download=True)
    return out


@router.get("", response_model=list[RecordingOut])
async def recordings(
    lesson_id: UUID | None = None, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> list[RecordingOut]:
    # Неудавшиеся записи видит только педагог — чтобы знать, что файла не будет.
    query = select(Recording).where(
        or_(
            (Recording.teacher_id == principal.user_id) & Recording.status.in_((RECORDING, READY, FAILED)),
            Recording.viewer_ids.contains([principal.user_id]) & Recording.status.in_((RECORDING, READY)),
        ),
    )
    if lesson_id:
        query = query.where(Recording.lesson_id == lesson_id)
    rows = (await session.execute(query.order_by(Recording.started_at.desc()).limit(100))).scalars().all()
    return [await _out(r, principal) for r in rows]


@router.delete("/{recording_id}", status_code=204)
async def delete(recording_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> None:
    rec = await session.get(Recording, recording_id, with_for_update=True)
    if rec is None or rec.teacher_id != principal.user_id:
        raise ApiError(404, "recording_not_found", "Запись не найдена")
    if rec.status == RECORDING:
        raise ApiError(409, "recording_active", "Сначала остановите запись")
    if rec.status == FAILED:  # файла нет — просто скрываем
        rec.status = "expired"
        await session.commit()
        return
    await rooms.expire(session, rec)
    await session.commit()
