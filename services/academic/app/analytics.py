"""Расширенная аналитика (ТЗ, раздел 8): динамика по неделям, сравнение с классом, тепловая карта пропусков, сводная ведомость.
Считается по своим таблицам оценок и посещаемости: у каждой записи есть дата занятия, группа и предмет."""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from . import stats
from .models import Attendance, Grade
from .schemas import GradePoint, GroupReport, HeatDay, StudentLine, StudentReport, SubjectLine, SummaryLine, TrendPoint

MISSED = ("absent", "sick")


def local_day(dt: datetime, tz: ZoneInfo) -> date:
    return dt.astimezone(tz).date()


def week_of(dt: datetime, tz: ZoneInfo) -> date:
    d = local_day(dt, tz)
    return d - timedelta(days=d.weekday())


def trend(grades: Iterable[Grade], marks: Iterable[Attendance], tz: ZoneInfo) -> list[TrendPoint]:
    """Средний балл и посещаемость по неделям — только недели, где что-то было."""
    by_week_g: dict[date, list[int]] = defaultdict(list)
    by_week_a: dict[date, list[str]] = defaultdict(list)
    for g in grades:
        by_week_g[week_of(g.lesson_starts_at, tz)].append(g.value)
    for a in marks:
        by_week_a[week_of(a.lesson_starts_at, tz)].append(a.status)
    out = []
    for w in sorted(set(by_week_g) | set(by_week_a)):
        values, statuses = by_week_g.get(w, []), by_week_a.get(w, [])
        out.append(TrendPoint(
            week=w,
            average=round(sum(values) / len(values), 2) if values else None,
            attendance_rate=round(sum(s not in MISSED for s in statuses) / len(statuses), 3) if statuses else None,
        ))
    return out


def heatmap(marks: Iterable[Attendance], tz: ZoneInfo) -> list[HeatDay]:
    by_day: dict[date, list[str]] = defaultdict(list)
    for a in marks:
        by_day[local_day(a.lesson_starts_at, tz)].append(a.status)
    return [
        HeatDay(day=d, marked=len(s), missed=sum(x in MISSED for x in s), rate=round(sum(x in MISSED for x in s) / len(s), 3))
        for d, s in sorted(by_day.items())
    ]


def distribution(grades: Iterable[Grade]) -> dict[int, int]:
    out = {v: 0 for v in range(1, 6)}
    for g in grades:
        out[g.value] += 1
    return out


def group_report(
    title: str, subject: str | None, period: tuple[date, date], grades: Sequence[Grade], marks: Sequence[Attendance],
    current: set[UUID], names: dict[UUID, str], tz: ZoneInfo, extended: bool,
) -> GroupReport:
    by_g: dict[UUID, list[Grade]] = defaultdict(list)
    by_a: dict[UUID, list[Attendance]] = defaultdict(list)
    for g in grades:
        by_g[g.student_id].append(g)
    for a in marks:
        by_a[a.student_id].append(a)
    total = stats.compute(grades, marks)
    lines = []
    for sid in current | set(by_g) | set(by_a):
        s = stats.compute(by_g[sid], by_a[sid])
        delta = round(s.average - total.average, 2) if extended and s.average is not None and total.average is not None else None
        lines.append(StudentLine(id=sid, full_name=names.get(sid, "Ученик"), current=sid in current, stats=s, delta=delta,
                                 trend=trend(by_g[sid], [], tz) if extended else None))
    # Сверху — лучшие; без оценок — внизу, по алфавиту.
    lines.sort(key=lambda s: (s.stats.average is None, -(s.stats.average or 0), s.full_name))
    return GroupReport(
        title=title, subject=subject, period_from=period[0], period_to=period[1], extended=extended, stats=total, students=lines,
        distribution=distribution(grades) if extended else None,
        trend=trend(grades, marks, tz) if extended else None,
        heatmap=heatmap(marks, tz) if extended else None,
    )


def student_report(
    full_name: str, period: tuple[date, date], grades: Sequence[Grade], marks: Sequence[Attendance],
    class_grades: Sequence[Grade], type_names: dict[UUID, str], tz: ZoneInfo, extended: bool,
) -> StudentReport:
    """class_grades — оценки всех учеников групп, где учится ученик: для сравнения по предметам."""
    subjects = sorted({g.subject or "Без предмета" for g in grades} | {a.subject or "Без предмета" for a in marks})
    lines = []
    for subj in subjects:
        sg = [g for g in grades if (g.subject or "Без предмета") == subj]
        sa = [a for a in marks if (a.subject or "Без предмета") == subj]
        cg = [g.value for g in class_grades if (g.subject or "Без предмета") == subj]
        lines.append(SubjectLine(subject=subj, stats=stats.compute(sg, sa),
                                 class_average=round(sum(cg) / len(cg), 2) if extended and cg else None))
    return StudentReport(
        full_name=full_name, period_from=period[0], period_to=period[1], extended=extended, stats=stats.compute(grades, marks),
        subjects=lines,
        grades=[GradePoint(at=g.lesson_starts_at, value=g.value, subject=g.subject, grade_type=type_names.get(g.grade_type_id, ""),
                           comment=g.comment) for g in sorted(grades, key=lambda g: g.lesson_starts_at)] if extended else None,
        trend=trend(grades, marks, tz) if extended else None,
    )


def summary_line(group_id: UUID | None, title: str, students: set[UUID], grades: Sequence[Grade], marks: Sequence[Attendance]) -> SummaryLine:
    by_student: dict[UUID, list[int]] = defaultdict(list)
    for g in grades:
        by_student[g.student_id].append(g.value)
    below = sum(1 for v in by_student.values() if sum(v) / len(v) < 3)
    everyone = students | set(by_student) | {a.student_id for a in marks}
    return SummaryLine(group_id=group_id, title=title, students=len(everyone), stats=stats.compute(grades, marks), below_three=below)
