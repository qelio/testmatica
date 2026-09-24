"""Развёртка правила повторения в список дат.

Повторы считаются в часовом поясе педагога: «каждый вторник в 15:00» остаётся 15:00
по местному времени, даже если меняется смещение от UTC.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from testmatica_common.errors import ApiError


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ApiError(422, "invalid_timezone", f"Неизвестный часовой пояс: {name}") from None


def expand(
    first_start: datetime,
    tz_name: str,
    weekdays: list[int],
    interval_weeks: int,
    until: date | None,
    count: int | None,
    max_lessons: int,
    max_days: int,
) -> list[datetime]:
    """Вернуть начала занятий (UTC). weekdays: 0 — понедельник … 6 — воскресенье.

    Недели считаются от недели первого занятия: при interval_weeks=2 занятия идут
    в неделю первого занятия, через одну и т. д.
    """
    if until is None and count is None:
        raise ApiError(422, "repeat_unbounded", "Укажите дату окончания или количество занятий")
    tz = zone(tz_name)
    local = first_start.astimezone(tz)
    start_date = local.date()
    week0 = start_date - timedelta(days=start_date.weekday())
    limit_date = start_date + timedelta(days=max_days)
    if until is not None:
        limit_date = min(limit_date, until)
    wanted = set(weekdays) or {start_date.weekday()}

    result: list[datetime] = []
    day = start_date
    while day <= limit_date:
        week_index = (day - week0).days // 7
        if day.weekday() in wanted and week_index % interval_weeks == 0:
            result.append(datetime.combine(day, local.timetz().replace(tzinfo=None), tz).astimezone(UTC))
            if (count is not None and len(result) >= count) or len(result) >= max_lessons:
                break
        day += timedelta(days=1)

    if not result:
        raise ApiError(422, "repeat_empty", "По этому правилу не получилось ни одного занятия")
    return result
