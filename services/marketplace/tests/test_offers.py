from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import text
from testmatica_common.testing import make_envelope

from app.api import offers, trials
from app.deps import db

from .conftest import MATH, bearer, outbox, person

STUDENT = ("student",)


def body(**extra):
    today = date.today()
    return {
        "title": "ОГЭ по математике, 9 класс", "subject_id": MATH, "levels": ["5-9"], "description": "Разбираем все задания ОГЭ",
        "program": ["  Дроби ", "Проценты", ""], "price": 900, "min_students": 2, "max_students": 3,
        "enroll_until": (today + timedelta(days=5)).isoformat(),
        "schedule": {"weekdays": [2, 0], "time": "18:00", "duration_min": 60, "start_date": (today + timedelta(days=7)).isoformat(),
                     "lessons_count": 16, "timezone": "Europe/Moscow"},
    } | extra


async def test_offer_lifecycle(client, fakes):
    maria, a, b, c, d = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    await person(maria, "Мария Иванова")
    for s, n in ((a, "Аня"), (b, "Борис"), (c, "Вика"), (d, "Гоша")):
        await person(s, n, STUDENT)

    bad = await client.post("/offers", json=body(min_students=3, max_students=2), headers=bearer(maria))
    assert bad.status_code == 422
    late = await client.post("/offers", json=body(enroll_until=(date.today() + timedelta(days=10)).isoformat()), headers=bearer(maria))
    assert late.status_code == 422  # набор должен закончиться до первого занятия
    assert (await client.post("/offers", json=body(), headers=bearer(a, STUDENT))).status_code == 403
    o = (await client.post("/offers", json=body(), headers=bearer(maria))).json()
    assert o["program"] == ["Дроби", "Проценты"] and o["schedule"]["weekdays"] == [0, 2] and o["joinable"] and o["is_owner"]
    assert o["subject"]["name"] == "Математика" and o["share_url"].endswith(f"/groups/{o['id']}")

    catalog = (await client.get("/offers")).json()
    assert [x["id"] for x in catalog] == [o["id"]] and catalog[0]["students"] is None  # гостю — без списка учеников
    assert (await client.get(f"/tutors/{maria}/offers")).json()[0]["id"] == o["id"]

    # Запуск — только при минимуме.
    joined = (await client.post(f"/offers/{o['id']}/join", headers=bearer(a, STUDENT))).json()
    assert joined["enrolled"] and joined["enrolled_count"] == 1 and joined["seats_left"] == 2
    assert (await client.post(f"/offers/{o['id']}/start", headers=bearer(maria))).json()["error"]["code"] == "not_enough_students"
    await client.post(f"/offers/{o['id']}/join", headers=bearer(b, STUDENT))
    assert (await outbox("marketplace.group_offer.min_reached"))[0]["data"]["count"] == 2
    await client.post(f"/offers/{o['id']}/join", headers=bearer(c, STUDENT))
    full = await client.post(f"/offers/{o['id']}/join", headers=bearer(d, STUDENT))
    assert full.json()["error"]["code"] == "offer_full"
    # Вика передумала — место освободилось.
    assert (await client.post(f"/offers/{o['id']}/leave", headers=bearer(c, STUDENT))).json()["enrolled"] is False
    mine = (await client.get("/offers/mine", headers=bearer(maria))).json()[0]
    assert [s["full_name"] for s in mine["students"]] == ["Аня", "Борис"]

    # Лимит групп бесплатного тарифа — проверяется перед запуском.
    fakes.group_limited.add(str(maria))
    limited = await client.post(f"/offers/{o['id']}/start", headers=bearer(maria))
    assert limited.status_code == 403 and limited.json()["error"]["code"] == "plan_limit"
    fakes.group_limited.clear()
    started = (await client.post(f"/offers/{o['id']}/start", headers=bearer(maria))).json()
    assert started["status"] == "started"
    event = (await outbox("marketplace.group_offer.started"))[0]["data"]
    assert event["student_ids"] == [str(a), str(b)] and event["price"] == 900 and event["schedule"]["time"] == "18:00"
    assert (await client.put(f"/offers/{o['id']}", json=body(), headers=bearer(maria))).json()["error"]["code"] == "offer_locked"
    assert (await client.post(f"/offers/{o['id']}/leave", headers=bearer(a, STUDENT))).json()["error"]["code"] == "offer_started"

    # В идущую группу можно войти, пока есть места; затем педагог закрывает набор.
    late_join = (await client.post(f"/offers/{o['id']}/join", headers=bearer(d, STUDENT))).json()
    assert late_join["enrolled"]
    assert [e["data"]["started"] for e in await outbox("marketplace.group_offer.joined")][-1] is True
    closed = (await client.post(f"/offers/{o['id']}/cancel", headers=bearer(maria))).json()
    assert closed["status"] == "closed" and closed["joinable"] is False
    assert (await client.get("/offers/enrolled", headers=bearer(a, STUDENT))).json()[0]["id"] == o["id"]


async def test_private_offer_and_underfill(client):
    maria, a = uuid4(), uuid4()
    await person(maria, "Мария Иванова")
    o = (await client.post("/offers", json=body(private=True), headers=bearer(maria))).json()
    assert (await client.get("/offers")).json() == [] and (await client.get(f"/tutors/{maria}/offers")).json() == []
    assert (await client.get(f"/offers/{o['id']}")).json()["private"] is True  # по ссылке — открывается
    await client.post(f"/offers/{o['id']}/join", headers=bearer(a, STUDENT))

    # Срок набора прошёл, минимум не набран — недобор, записавшиеся получают уведомление.
    async with db.engine.begin() as conn:
        await conn.execute(text("UPDATE group_offers SET enroll_until = current_date - 1"))
    await offers.check_deadlines()
    view = (await client.get(f"/offers/{o['id']}", headers=bearer(maria))).json()
    assert view["status"] == "underfilled" and view["joinable"] is False
    assert (await outbox("marketplace.group_offer.underfilled"))[0]["data"]["student_ids"] == [str(a)]

    # Продлить набор: срок позже старого первого занятия — нужно сдвинуть и его.
    far = (date.today() + timedelta(days=20)).isoformat()
    assert (await client.post(f"/offers/{o['id']}/extend", json={"enroll_until": far}, headers=bearer(maria))).status_code == 422
    ext = (await client.post(f"/offers/{o['id']}/extend", json={"enroll_until": far, "start_date": far}, headers=bearer(maria))).json()
    assert ext["status"] == "recruiting" and ext["joinable"] and ext["schedule"]["start_date"] == far

    cancelled = (await client.post(f"/offers/{o['id']}/cancel", headers=bearer(maria))).json()
    assert cancelled["status"] == "cancelled"
    assert (await outbox("marketplace.group_offer.cancelled"))[0]["data"]["student_ids"] == [str(a)]


async def test_trial_followup(client):
    maria, olya = uuid4(), uuid4()
    await person(maria, "Мария Иванова")
    await person(olya, "Оля Смирнова", STUDENT)
    lesson = uuid4()
    envelope = make_envelope("schedule.lesson.trial_finished", {
        "lesson_ids": [str(lesson)], "teacher_id": str(maria), "teacher_name": "Мария Иванова", "student_ids": [str(olya)],
        "title": "Оля Смирнова", "subject": "Математика", "starts_at": "2026-09-26T15:00:00+00:00", "trial": True,
        "kind": "individual"})
    for _ in range(2):  # повтор события — одно предложение
        async with db.sessionmaker() as s, s.begin():
            await trials.on_schedule_event(envelope, s)
    assert len(await outbox("marketplace.trial.followup_created")) == 1
    [p] = (await client.get("/trials/pending", headers=bearer(olya, STUDENT))).json()
    assert p["tutor"]["full_name"] == "Мария Иванова" and p["reviewed"] is False and p["title"] == "Индивидуальное занятие · Математика"

    done = (await client.post(f"/trials/{lesson}/answer", json={"decision": "continue", "comment": "Понравилось!"},
                              headers=bearer(olya, STUDENT))).json()
    assert done["status"] == "continue"
    answered = (await outbox("marketplace.trial.answered"))[0]["data"]
    assert answered["decision"] == "continue" and answered["student_name"] == "Оля Смирнова"
    assert (await client.get("/trials/pending", headers=bearer(olya, STUDENT))).json() == []
    again = await client.post(f"/trials/{lesson}/answer", json={"decision": "stop"}, headers=bearer(olya, STUDENT))
    assert again.json()["error"]["code"] == "trial_answered"
