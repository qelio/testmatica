from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import update

from app.api import competencies, requests
from app.deps import db
from app.models import LessonRequest

from .conftest import MATH, PHYSICS, bearer, outbox, person
from .test_tutors import publish

S = ("student",)


async def comps(client):
    await competencies.ensure_defaults()  # в фейковом справочнике есть «Математика»
    return (await client.get("/competencies", params={"subject_id": MATH})).json()


def body(**extra):
    return {"subject_id": MATH, "goal": "ege", "price": 1200, "duration_min": 60, "comment": "Хочу на 80+",
            "schedule": {"weekdays": [1, 3, 1], "time_from": "17:00", "time_to": "20:00"}} | extra


async def test_direct_request_and_agreement(client):
    tutor, pupil = uuid4(), uuid4()
    await person(tutor, "Мария Иванова")
    await person(pupil, "Оля Смирнова", S)
    await publish(client, tutor)
    items = await comps(client)
    assert [c["title"] for c in items][:2] == ["Арифметика и дроби", "Проценты"]

    req = (await client.post("/requests", json=body(tutor_id=str(tutor), current_ids=[items[0]["id"]], desired_ids=[items[3]["id"]]),
                             headers=bearer(pupil, S))).json()
    assert req["direct"] and req["schedule"]["weekdays"] == [1, 3] and req["current"] == ["Арифметика и дроби"]
    [resp] = req["responses"]
    assert resp["tutor"]["full_name"] == "Мария Иванова" and resp["price"] == 1200 and resp["proposed_by"] == "student"
    created = (await outbox("marketplace.response.created"))[0]["data"]
    assert created["response_id"] == resp["id"] and created["student_id"] == str(pupil)
    assert (await outbox("marketplace.request.created"))[0]["data"]["tutor_ids"] == [str(tutor)]

    # Торг: ученик не может «договориться» со своей же ценой; репетитор предлагает свою — теперь соглашается ученик.
    own = await client.post(f"/responses/{resp['id']}/agree", headers=bearer(pupil, S))
    assert own.json()["error"]["code"] == "own_proposal"
    neg = (await client.post(f"/responses/{resp['id']}/price", json={"price": 1500}, headers=bearer(tutor))).json()
    assert neg["role"] == "tutor" and neg["can_agree"] is False and neg["response"]["price"] == 1500
    student_view = (await client.get(f"/responses/{resp['id']}", headers=bearer(pupil, S))).json()
    assert student_view["can_agree"] is True
    assert (await client.get(f"/responses/{resp['id']}", headers=bearer(uuid4()))).status_code == 404

    done = (await client.post(f"/responses/{resp['id']}/agree", headers=bearer(pupil, S))).json()
    assert done["response"]["status"] == "agreed" and done["request"]["status"] == "agreed"
    deal = (await outbox("marketplace.deal.agreed"))[0]["data"]
    assert (deal["price"], deal["duration_min"], deal["tutor_id"]) == (1500, 60, str(tutor))
    after = await client.post(f"/responses/{resp['id']}/price", json={"price": 1000}, headers=bearer(tutor))
    assert after.json()["error"]["code"] == "negotiation_closed"


async def test_open_request_many_responses(client):
    a, b, c, pupil = uuid4(), uuid4(), uuid4(), uuid4()
    for t, n in ((a, "Анна"), (b, "Борис"), (c, "Вера")):
        await person(t, n)
    await publish(client, a)
    await publish(client, b)
    await publish(client, c, subject_ids=[PHYSICS])
    req = (await client.post("/requests", json=body(), headers=bearer(pupil, S))).json()
    assert not req["direct"] and req["responses"] == []
    notified = (await outbox("marketplace.request.created"))[0]["data"]["tutor_ids"]
    assert sorted(notified) == sorted([str(a), str(b)])  # только репетиторы предмета

    # Репетитор видит заявки своих предметов; физик — нет (пока не попросит все).
    assert [r["id"] for r in (await client.get("/requests/open", headers=bearer(a))).json()] == [req["id"]]
    assert (await client.get("/requests/open", headers=bearer(c))).json() == []
    assert len((await client.get("/requests/open", params={"all_subjects": True}, headers=bearer(c))).json()) == 1
    hidden = uuid4()
    no_profile = await client.post(f"/requests/{req['id']}/respond", json={}, headers=bearer(hidden))
    assert no_profile.json()["error"]["code"] == "profile_not_published"

    ra = (await client.post(f"/requests/{req['id']}/respond", json={"message": "Готова помочь"}, headers=bearer(a))).json()
    rb = (await client.post(f"/requests/{req['id']}/respond", json={"price": 1800}, headers=bearer(b))).json()
    assert ra["response"]["proposed_by"] == "student" and ra["can_agree"] is True  # репетитор согласен на цену ученика
    assert rb["response"]["proposed_by"] == "tutor"
    again = await client.post(f"/requests/{req['id']}/respond", json={}, headers=bearer(a))
    assert again.json()["error"]["code"] == "already_responded"
    mine = (await client.get("/requests/mine", headers=bearer(pupil, S))).json()[0]
    assert sorted(r["tutor"]["full_name"] for r in mine["responses"]) == ["Анна", "Борис"]
    assert [r["id"] for r in (await client.get("/responses/mine", headers=bearer(b))).json()[0]["responses"]] == [rb["response"]["id"]]

    # Ученик соглашается с Борисом — отклик Анны закрывается, заявка тоже.
    await client.post(f"/responses/{rb['response']['id']}/agree", headers=bearer(pupil, S))
    closed = [e["data"] for e in await outbox("marketplace.response.closed")]
    assert [(x["tutor_id"], x["reason"]) for x in closed] == [(str(a), "agreed_other")]
    assert (await client.get("/requests/open", headers=bearer(a))).json() == []


async def test_close_expire_and_limits(client):
    tutor, pupil = uuid4(), uuid4()
    await publish(client, tutor)
    req = (await client.post("/requests", json=body(), headers=bearer(pupil, S))).json()
    r = (await client.post(f"/requests/{req['id']}/respond", json={}, headers=bearer(tutor))).json()
    closed = (await client.post(f"/requests/{req['id']}/close", headers=bearer(pupil, S))).json()
    assert closed["status"] == "closed" and closed["responses"][0]["status"] == "closed"
    assert (await client.post(f"/responses/{r['response']['id']}/agree", headers=bearer(tutor))).status_code == 409

    old = (await client.post("/requests", json=body(), headers=bearer(pupil, S))).json()
    async with db.sessionmaker() as s, s.begin():
        await s.execute(update(LessonRequest).where(LessonRequest.id == UUID(old["id"])).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    await requests.expire_requests()
    assert (await client.get("/requests/mine", headers=bearer(pupil, S))).json()[0]["status"] == "expired"

    for _ in range(5):
        await client.post("/requests", json=body(), headers=bearer(pupil, S))
    limit = await client.post("/requests", json=body(), headers=bearer(pupil, S))
    assert limit.json()["error"]["code"] == "too_many_requests"
    foreign_comp = await client.post("/requests", json=body(subject_id=PHYSICS, current_ids=[(await comps(client))[0]["id"]]),
                                     headers=bearer(uuid4(), S))
    assert foreign_comp.json()["error"]["code"] == "unknown_competency"
    assert (await client.post("/requests", json=body(tutor_id=str(pupil)), headers=bearer(pupil, S))).status_code == 422


async def test_competencies_managed_by_moderators(client):
    mod = bearer(uuid4(), ("moderator",))
    assert (await client.post("/competencies", json={"subject_id": MATH, "title": "X"}, headers=bearer(uuid4()))).status_code == 403
    c = (await client.post("/competencies", json={"subject_id": MATH, "title": "  Параметры  "}, headers=mod)).json()
    assert c["title"] == "Параметры"
    assert (await client.patch(f"/competencies/{c['id']}", json={"title": "Задачи с параметром"}, headers=mod)).json()["title"] == "Задачи с параметром"
    assert (await client.delete(f"/competencies/{c['id']}", headers=mod)).status_code == 204
