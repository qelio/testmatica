"""Автопроставление оценки из теста или ДЗ (assessment.attempt.graded), если педагог это настроил."""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError
from testmatica_common.messaging import Envelope

from .api.journal import _grade_event
from .deps import schedule
from .models import Grade, GradeType

log = logging.getLogger(__name__)


KINDS = {"live": "Тест на уроке", "homework": "ДЗ", "test": "Тест"}


def _comment(d: dict) -> str:
    text = f"{KINDS.get(d.get('kind'), 'Тест')} «{d['title']}»: {d['percent']:g}% ({d['score']:g} из {d['max_score']:g})"
    if (d.get("attempts") or 1) > 1:
        text += f", лучшая из {d['attempts']} попыток"
    return text


async def on_assessment_event(envelope: Envelope, session: AsyncSession) -> None:
    if envelope.type != "assessment.attempt.graded":
        return
    d = envelope.data
    if not (d.get("to_journal") and d.get("lesson_id") and d.get("grade_type_id")):
        return
    grade_type = await session.get(GradeType, UUID(d["grade_type_id"]))
    if grade_type is None:
        log.warning("test grade skipped: unknown grade type", extra={"attempt_id": d["attempt_id"]})
        return
    try:
        lesson = await schedule.get(f"/internal/lessons/{d['lesson_id']}", params={"teacher_id": d["teacher_id"]})
    except ApiError as e:
        if e.status == 404:  # урок удалён — ставить некуда
            log.warning("test grade skipped: lesson not found", extra={"attempt_id": d["attempt_id"]})
            return
        raise  # расписание недоступно — сообщение повторится
    if lesson["status"] != "scheduled":
        return

    student_id, ref = UUID(d["student_id"]), UUID(d["assignment_id"])
    grade = await session.scalar(
        select(Grade).where(Grade.source == "test", Grade.source_ref == ref, Grade.student_id == student_id).with_for_update()
    )
    event = "academic.grade.updated"
    if grade is None:
        grade = Grade(
            teacher_id=UUID(d["teacher_id"]), student_id=student_id, lesson_id=UUID(lesson["id"]),
            lesson_starts_at=datetime.fromisoformat(lesson["starts_at"]),
            group_id=UUID(lesson["group_id"]) if lesson["group_id"] else None, subject=lesson["subject"],
            grade_type_id=grade_type.id, source="test", source_ref=ref, value=d["grade"], comment=_comment(d),
        )
        session.add(grade)
        event = "academic.grade.created"
    else:
        # Переназначили и ученик пересдал — в журнале последняя попытка.
        grade.value, grade.comment = d["grade"], _comment(d)
    await session.flush()
    await _grade_event(session, event, grade, grade_type, UUID(d["teacher_id"]))
