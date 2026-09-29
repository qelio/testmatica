from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import text

from app.api.game import level_for, streaks
from app.deps import db

from .conftest import CHOICE, bearer, link, student


def test_levels_and_streaks():
    assert (level_for(0).number, level_for(49).number, level_for(50).number, level_for(150).number) == (1, 1, 2, 3)
    assert level_for(60).xp_from == 50 and level_for(60).xp_to == 150 and level_for(60).title == "Исследователь"
    today = date(2026, 9, 29)
    d = lambda n: today - timedelta(days=n)  # noqa: E731
    assert streaks({d(1), d(2), d(3)}, today) == (3, 3)  # сегодня ещё не решал — серия не оборвалась
    assert streaks({d(0), d(1), d(5), d(6), d(7), d(8)}, today) == (2, 4)
    assert streaks({d(2)}, today) == (0, 1)


async def test_my_game(client):
    teacher, pupil = uuid4(), uuid4()
    task = (await client.post("/tasks", json=CHOICE, headers=bearer(teacher))).json()
    await link(teacher, pupil)
    right = next(o["id"] for o in task["options"] if o["is_correct"])
    wrong = next(o["id"] for o in task["options"] if not o["is_correct"])

    empty = (await client.get("/me/game", headers=student(pupil))).json()
    assert empty["xp"] == 0 and empty["level"]["number"] == 1 and not any(a["earned"] for a in empty["achievements"])

    async def send(option):
        body = {"context_type": "practice", "context_id": str(uuid4()), "answer": {"option_ids": [option]}}
        assert (await client.post(f"/tasks/{task['id']}/submissions", json=body, headers=student(pupil))).status_code == 201

    for _ in range(3):
        await send(wrong)
    await send(right)
    await send(right)  # повторное решение опыт не добавляет
    # Вчера тоже занимался — серия 2 дня.
    async with db.engine.begin() as conn:
        await conn.execute(text("UPDATE submissions SET created_at = created_at - interval '1 day' "
                                "WHERE id = (SELECT id FROM submissions WHERE student_id = :p ORDER BY created_at LIMIT 1)"), {"p": pupil})

    game = (await client.get("/me/game", params={"tz": "Asia/Yekaterinburg"}, headers=student(pupil))).json()
    earned = {a["code"] for a in game["achievements"] if a["earned"]}
    assert game["solved"] == 1 and game["xp"] == 10 + 2 * 5 and game["streak"] == 2 and game["today_active"]
    assert game["week"][-2:] == [True, True] and earned == {"first", "stubborn"}
    ten = next(a for a in game["achievements"] if a["code"] == "ten")
    assert (ten["current"], ten["target"]) == (1, 10)
    assert (await client.get("/me/game", headers=bearer(teacher))).status_code == 403
