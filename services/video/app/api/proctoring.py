"""Прокторинг: вход в комнату наблюдения и записи экранов учеников (ТЗ, раздел 7)."""

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal
from testmatica_common.errors import ApiError

from .. import people, proctoring, storage
from ..deps import assessment, auth, db, livekit
from ..models import FAILED, READY, RECORDING, ProctorRecording
from ..schemas import ProctorJoinOut, ProctorRecordingOut, ProctorStudentOut

router = APIRouter(prefix="/proctoring", tags=["proctoring"])

MAX_PARTICIPANTS = 16 + 1  # до 15 учеников и педагог; +1 — запас на переподключение


async def _access(assignment_id: UUID, p: Principal) -> dict:
    """Кто пользователь в прокторинге — решает assessment (педагог назначения или ученик с идущей попыткой)."""
    return await assessment.get(f"/internal/proctoring/{assignment_id}", params={"user_id": str(p.user_id)})


@router.post("/{assignment_id}/join", response_model=ProctorJoinOut)
async def join(assignment_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> ProctorJoinOut:
    access = await _access(assignment_id, principal)
    teacher = access["role"] == "teacher"
    if access["closed"] and not teacher:
        raise ApiError(409, "assignment_closed", "Тест завершён")
    if not teacher and not access["attempt_id"]:
        raise ApiError(409, "no_attempt", "Сначала начните тест")
    room = proctoring.room_name(assignment_id)
    await livekit.create_room(room, MAX_PARTICIPANTS)
    name = (await people.names(session, [principal.user_id])).get(principal.user_id, "Педагог" if teacher else "Ученик")
    meta = {"role": access["role"], "teacher_id": access["teacher_id"], "title": access["title"], "attempt_id": access.get("attempt_id")}
    token = livekit.proctor_token(room, str(principal.user_id), name, teacher, meta, timedelta(hours=6))
    return ProctorJoinOut(
        url=livekit.public_url, token=token, role=access["role"], title=access["title"],
        students=[ProctorStudentOut(**s) for s in access.get("students", [])],
    )


@router.get("/{assignment_id}/recordings", response_model=list[ProctorRecordingOut])
async def recordings(assignment_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> list[ProctorRecordingOut]:
    """Записи экранов — только педагогу назначения."""
    access = await _access(assignment_id, principal)
    if access["role"] != "teacher":
        raise ApiError(404, "assignment_not_found", "Тест не найден")
    rows = (await session.execute(
        select(ProctorRecording).where(ProctorRecording.assignment_id == assignment_id,
                                       ProctorRecording.status.in_((RECORDING, READY, FAILED)))
        .order_by(ProctorRecording.started_at)
    )).scalars().all()
    names = await people.names(session, [r.student_id for r in rows])
    out = []
    for r in rows:
        ext = r.key.rsplit(".", 1)[1] if "." in r.key.rsplit("/", 1)[-1] else "webm"
        filename = f"Прокторинг — {names.get(r.student_id, 'ученик')} — {r.started_at:%d.%m.%Y %H-%M}.{ext}"
        ready = r.status == READY
        out.append(ProctorRecordingOut(
            id=r.id, student_id=r.student_id, student_name=names.get(r.student_id, "Ученик"), attempt_id=r.attempt_id, status=r.status,
            started_at=r.started_at, duration_s=r.duration_s, expires_at=r.expires_at,
            url=await storage.url(r.key, filename, download=False) if ready else None,
            download_url=await storage.url(r.key, filename, download=True) if ready else None,
        ))
    return out


