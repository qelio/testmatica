"""Базовая аналитика: средний балл и посещаемость."""

from collections.abc import Iterable

from .models import Attendance, Grade
from .schemas import Stats


def compute(grades: Iterable[Grade], attendance: Iterable[Attendance]) -> Stats:
    values = [g.value for g in grades]
    counts = {"present": 0, "late": 0, "absent": 0, "sick": 0}
    for a in attendance:
        counts[a.status] += 1
    marked = sum(counts.values())
    attended = counts["present"] + counts["late"]
    return Stats(
        average=round(sum(values) / len(values), 2) if values else None,
        grades_count=len(values),
        attendance_rate=round(attended / marked, 3) if marked else None,
        **counts,
    )
