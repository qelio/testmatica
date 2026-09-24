"""Оценки и посещаемость ученика — от всех педагогов в одном месте."""

from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_STUDENT, Principal
from testmatica_common.errors import ApiError

from .. import people, stats
from ..deps import auth, db
from ..models import Attendance, Grade
from ..schemas import MyGrades, SubjectGrades
from .journal import grade_out, type_names

router = APIRouter(prefix="/me", tags=["me"])

NO_SUBJECT = "Без предмета"


@router.get("/grades", response_model=MyGrades)
async def my_grades(
    start: datetime = Query(alias="from"),
    end: datetime = Query(alias="to"),
    principal: Principal = Depends(auth.require(ROLE_STUDENT)),
    session: AsyncSession = Depends(db.session),
) -> MyGrades:
    if end <= start or end - start > timedelta(days=370):
        raise ApiError(422, "invalid_range", "Период — не больше года")
    in_period = (Grade.student_id == principal.user_id, Grade.lesson_starts_at >= start, Grade.lesson_starts_at < end)
    grades = (await session.execute(select(Grade).where(*in_period).order_by(Grade.lesson_starts_at.desc()))).scalars().all()
    marks = (
        await session.execute(
            select(Attendance).where(
                Attendance.student_id == principal.user_id,
                Attendance.lesson_starts_at >= start,
                Attendance.lesson_starts_at < end,
            )
        )
    ).scalars().all()

    by_subject_grades: dict[str, list[Grade]] = defaultdict(list)
    by_subject_marks: dict[str, list[Attendance]] = defaultdict(list)
    teachers: dict[str, set] = defaultdict(set)
    for g in grades:
        key = g.subject or NO_SUBJECT
        by_subject_grades[key].append(g)
        teachers[key].add(g.teacher_id)
    for a in marks:
        key = a.subject or NO_SUBJECT
        by_subject_marks[key].append(a)
        teachers[key].add(a.teacher_id)

    names = await people.names(session, {t for ts in teachers.values() for t in ts})
    types = await type_names(session)
    subjects = [
        SubjectGrades(
            subject=subject,
            teacher_names=sorted(names.get(t, people.UNKNOWN_NAME) for t in teachers[subject]),
            stats=stats.compute(by_subject_grades[subject], by_subject_marks[subject]),
            grades=[grade_out(g, types) for g in by_subject_grades[subject]],
        )
        for subject in sorted(teachers, key=lambda s: (s == NO_SUBJECT, s))
    ]
    return MyGrades(subjects=subjects, stats=stats.compute(grades, marks))
