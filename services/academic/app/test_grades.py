"""Автопроставление оценки из теста или ДЗ (assessment.attempt.graded), если педагог это настроил.

Оценка встаёт отдельной колонкой работы — без привязки к уроку (решение №34): дата колонки — когда работа назначена,
для работы группе — в журнале группы. Переназначение или правка педагогом обновляют ту же оценку."""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from .api.journal import _grade_event
from .models import Grade, GradeType

log = logging.getLogger(__name__)


KINDS = {"live": "Тест на уроке", "homework": "ДЗ", "test": "Тест"}


def _comment(d: dict) -> str:
    text = f"{KINDS.get(d.get('kind'), 'Тест')} «{d['title']}»: {d['percent']:g}% ({d['score']:g} из {d['max_score']:g})"
    if (d.get("attempts") or 1) > 1:
        text += f", лучшая из {d['attempts']} попыток"
    if d.get("by_teacher"):
        text += ", оценку поставил педагог"
    return text


async def on_assessment_event(envelope: Envelope, session: AsyncSession) -> None:
    if envelope.type != "assessment.attempt.graded":
        return
    d = envelope.data
    if not (d.get("to_journal") and d.get("grade_type_id")):
        return
    grade_type = await session.get(GradeType, UUID(d["grade_type_id"]))
    if grade_type is None:
        log.warning("test grade skipped: unknown grade type", extra={"attempt_id": d["attempt_id"]})
        return

    student_id, ref = UUID(d["student_id"]), UUID(d["assignment_id"])
    grade = await session.scalar(
        select(Grade).where(Grade.source == "test", Grade.source_ref == ref, Grade.student_id == student_id).with_for_update()
    )
    event = "academic.grade.updated"
    if grade is None:
        assigned = datetime.fromisoformat(d["assigned_at"]) if d.get("assigned_at") else envelope.occurred_at
        grade = Grade(
            teacher_id=UUID(d["teacher_id"]), student_id=student_id, lesson_id=None, lesson_starts_at=assigned,
            group_id=UUID(d["group_id"]) if d.get("group_id") else None, subject=None, title=d["title"],
            grade_type_id=grade_type.id, source="test", source_ref=ref, value=d["grade"], comment=_comment(d),
        )
        session.add(grade)
        event = "academic.grade.created"
    else:
        # Пересдал после переназначения или педагог изменил оценку — в журнале обновлённая.
        grade.value, grade.comment = d["grade"], _comment(d)
    await session.flush()
    await _grade_event(session, event, grade, grade_type, UUID(d["teacher_id"]))
