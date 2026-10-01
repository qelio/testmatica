"""Живые обновления тестов через WebSocket чата: педагог сразу видит, что ученик начал или сдал работу,
ученик — что педагог завершил или проверил её, сервер видеосвязи увидел показ экрана (прокторинг). Без записи в БД."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from . import realtime

KINDS = {
    "assessment.attempt.started": "started",
    "assessment.attempt.submitted": "submitted",
    "assessment.attempt.screen": "screen",
    "assessment.attempt.reviewed": "reviewed",
}


async def on_identity_event(envelope: Envelope, session: AsyncSession) -> None:
    """Педагог вывел ученика из аккаунта — открытые вкладки ученика выходят сразу."""
    if envelope.type == "identity.user.signed_out":
        await realtime.publish([UUID(envelope.data["user_id"])], {"type": "logout"})


async def on_assessment_event(envelope: Envelope, session: AsyncSession) -> None:
    kind = KINDS.get(envelope.type)
    if kind is None:
        return
    d = envelope.data
    await realtime.publish([UUID(d["teacher_id"]), UUID(d["student_id"])], {
        "type": "assignment", "kind": kind, "assignment_id": d["assignment_id"], "attempt_id": d["attempt_id"],
        "student_id": d["student_id"], "by_teacher": bool(d.get("by_teacher")), "sharing": d.get("sharing"),
    })
