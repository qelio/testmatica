"""«Мои успехи» ученика: опыт, уровень, серия дней, достижения (решение №25).

Всё считается на лету по решениям и сданным тестам — отдельно ничего не хранится,
поэтому правила можно менять без миграций, а прогресс не расходится с настоящими решениями."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_STUDENT, Principal

from ..deps import auth, db

router = APIRouter(tags=["game"])
student = auth.require(ROLE_STUDENT)

XP_TASK = 10  # задача решена (засчитывается один раз)
XP_TEST = 20  # тест сдан
XP_TEST_EXCELLENT = 15  # доплата за тест на 90% и выше
XP_DAY = 5  # день, когда ученик что-то решал

LEVEL_TITLES = ["Новичок", "Исследователь", "Решатель", "Знаток", "Эрудит", "Мастер", "Профи", "Гуру", "Легенда"]

_OK = "(s.status = 'correct' OR (s.status = 'reviewed' AND s.score >= 0.5))"


class Level(BaseModel):
    number: int
    title: str
    xp_from: int  # опыт, с которого начинается уровень
    xp_to: int  # опыт следующего уровня


class Achievement(BaseModel):
    code: str
    title: str
    text: str
    icon: str  # имя иконки на фронте
    earned: bool
    current: int
    target: int


class Game(BaseModel):
    xp: int
    level: Level
    streak: int  # дней подряд, включая сегодня или вчера
    best_streak: int
    today_active: bool
    week: list[bool]  # последние 7 дней, последний — сегодня
    solved: int
    tests: int
    achievements: list[Achievement]


def level_for(xp: int) -> Level:
    """Каждый следующий уровень на 50 опыта дороже: 0, 50, 150, 300, 500…"""
    n, start, step = 1, 0, 50
    while xp >= start + step:
        start, step, n = start + step, step + 50, n + 1
    title = LEVEL_TITLES[n - 1] if n <= len(LEVEL_TITLES) else f"{LEVEL_TITLES[-1]} {n - len(LEVEL_TITLES) + 1}"
    return Level(number=n, title=title, xp_from=start, xp_to=start + step)


def streaks(days: set[date], today: date) -> tuple[int, int]:
    """Текущая серия (не обрывается, пока сегодня ещё не решал) и лучшая."""
    current, d = 0, today if today in days else today - timedelta(days=1)
    while d in days:
        current, d = current + 1, d - timedelta(days=1)
    best = run = 0
    prev: date | None = None
    for day in sorted(days):
        run = run + 1 if prev and day - prev == timedelta(days=1) else 1
        best, prev = max(best, run), day
    return current, max(best, current)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Europe/Moscow")


@router.get("/me/game", response_model=Game)
async def my_game(
    tz: str = Query("Europe/Moscow", max_length=64, description="Часовой пояс ученика — для границ дней"),
    principal: Principal = Depends(student),
    session: AsyncSession = Depends(db.session),
) -> Game:
    zone = _zone(tz)
    params = {"me": principal.user_id}
    stats = (await session.execute(text(f"""
        SELECT count(DISTINCT s.task_id) FILTER (WHERE {_OK}) AS solved,
               count(DISTINCT s.task_id) FILTER (WHERE {_OK} AND t.type = 'code') AS code_solved
        FROM submissions s JOIN tasks t ON t.id = s.task_id
        WHERE s.student_id = :me
    """), params)).one()
    # Задачи, решённые после трёх и более неудачных попыток.
    stubborn = (await session.execute(text(f"""
        SELECT count(*) FROM (
            SELECT s.task_id FROM submissions s WHERE s.student_id = :me
            GROUP BY s.task_id
            HAVING bool_or({_OK})
               AND count(*) FILTER (WHERE s.status = 'incorrect' AND s.created_at <
                   (SELECT min(x.created_at) FROM submissions x WHERE x.student_id = :me AND x.task_id = s.task_id
                    AND (x.status = 'correct' OR (x.status = 'reviewed' AND x.score >= 0.5)))) >= 3
        ) q
    """), params)).scalar_one()
    tests = (await session.execute(text("""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE percent >= 90) AS excellent,
               count(*) FILTER (WHERE percent >= 100) AS perfect
        FROM attempts WHERE student_id = :me AND status = 'submitted'
    """), params)).one()
    moments = (await session.execute(text("""
        SELECT created_at FROM submissions WHERE student_id = :me
        UNION ALL SELECT submitted_at FROM attempts WHERE student_id = :me AND submitted_at IS NOT NULL
    """), params)).scalars()
    days = {m.astimezone(zone).date() for m in moments if isinstance(m, datetime)}
    today = datetime.now(zone).date()
    current, best = streaks(days, today)

    xp = stats.solved * XP_TASK + tests.total * XP_TEST + tests.excellent * XP_TEST_EXCELLENT + len(days) * XP_DAY

    def a(code: str, title: str, text_: str, icon: str, cur: int, target: int) -> Achievement:
        return Achievement(code=code, title=title, text=text_, icon=icon, earned=cur >= target, current=min(cur, target), target=target)

    achievements = [
        a("first", "Первый шаг", "Решить первую задачу", "footprints", stats.solved, 1),
        a("ten", "Десятка", "Решить 10 задач", "target", stats.solved, 10),
        a("fifty", "Полсотни", "Решить 50 задач", "medal", stats.solved, 50),
        a("hundred", "Сотня", "Решить 100 задач", "trophy", stats.solved, 100),
        a("streak3", "Огонёк", "Заниматься 3 дня подряд", "flame", best, 3),
        a("streak7", "Неделя в строю", "Заниматься 7 дней подряд", "calendar-check", best, 7),
        a("test", "Первый тест", "Сдать тест", "clipboard-check", tests.total, 1),
        a("excellent", "Отличник", "Сдать тест на 90% и выше", "star", tests.excellent, 1),
        a("perfect", "Без единой ошибки", "Сдать тест на 100%", "gem", tests.perfect, 1),
        a("coder", "Программист", "Решить задачу с кодом", "code", stats.code_solved, 1),
        a("stubborn", "Упорство", "Решить задачу после трёх неудачных попыток", "mountain", stubborn, 1),
    ]
    return Game(
        xp=xp, level=level_for(xp), streak=current, best_streak=best, today_active=today in days,
        week=[today - timedelta(days=i) in days for i in range(6, -1, -1)],
        solved=stats.solved, tests=tests.total, achievements=achievements,
    )

