from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from testmatica_common.errors import ApiError

from app.recurrence import expand

MSK = ZoneInfo("Europe/Moscow")


def local(dt: datetime, tz="Europe/Moscow") -> str:
    return dt.astimezone(ZoneInfo(tz)).strftime("%a %d.%m %H:%M")


def test_weekly_by_weekdays_with_count():
    first = datetime(2026, 9, 29, 15, 0, tzinfo=MSK)  # вторник
    result = expand(first, "Europe/Moscow", [1, 3], 1, None, 5, 200, 366)
    assert [local(d) for d in result] == [
        "Tue 29.09 15:00",
        "Thu 01.10 15:00",
        "Tue 06.10 15:00",
        "Thu 08.10 15:00",
        "Tue 13.10 15:00",
    ]
    assert all(d.tzinfo == UTC for d in result)


def test_every_two_weeks_until_date():
    first = datetime(2026, 9, 28, 10, 0, tzinfo=MSK)  # понедельник
    result = expand(first, "Europe/Moscow", [0], 2, date(2026, 11, 9), None, 200, 366)
    assert [local(d) for d in result] == ["Mon 28.09 10:00", "Mon 12.10 10:00", "Mon 26.10 10:00", "Mon 09.11 10:00"]


def test_local_time_is_kept_across_dst():
    # В Берлине 25.10.2026 переход на зимнее время: смещение UTC меняется, местное время — нет.
    tz = ZoneInfo("Europe/Berlin")
    first = datetime(2026, 10, 20, 18, 0, tzinfo=tz)
    result = expand(first, "Europe/Berlin", [1], 1, None, 2, 200, 366)
    assert [local(d, "Europe/Berlin") for d in result] == ["Tue 20.10 18:00", "Tue 27.10 18:00"]
    assert [d.hour for d in result] == [16, 17]


def test_first_day_not_in_weekdays_starts_from_next_match():
    first = datetime(2026, 9, 29, 15, 0, tzinfo=MSK)  # вторник, а выбрана среда
    result = expand(first, "Europe/Moscow", [2], 1, None, 1, 200, 366)
    assert [local(d) for d in result] == ["Wed 30.09 15:00"]


def test_limits():
    first = datetime(2026, 9, 28, 10, 0, tzinfo=MSK)
    assert len(expand(first, "Europe/Moscow", list(range(7)), 1, None, 1000, 200, 366)) == 200
    with pytest.raises(ApiError):
        expand(first, "Europe/Moscow", [0], 1, date(2026, 9, 1), None, 200, 366)
    with pytest.raises(ApiError):
        expand(first, "Mars/Olympus", [0], 1, None, 3, 200, 366)
