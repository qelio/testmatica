from uuid import uuid4

from .conftest import MATH, PHYSICS, bearer, decide, outbox, person

FULL = {
    "headline": "Математика ЕГЭ и ОГЭ, 10 лет",
    "about": "Готовлю к ЕГЭ и ОГЭ по профильной математике. Объясняю через задачи, даю домашние задания и разбор.",
    "subject_ids": [MATH], "levels": ["5-9", "10-11"], "formats": ["individual", "group"], "price": 1500, "experience_years": 10,
}


async def publish(client, user, **extra):
    resp = await client.put("/me/profile", json=FULL | {"published": True} | extra, headers=bearer(user))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_profile_publish_rules(client, fakes):
    maria, student = uuid4(), uuid4()
    await person(maria, "Мария Иванова")
    empty = (await client.get("/me/profile", headers=bearer(maria))).json()
    assert empty["profile"]["published"] is False and "Предметы" in empty["missing"]

    incomplete = await client.put("/me/profile", json={"published": True, "headline": "Коротко"}, headers=bearer(maria))
    assert incomplete.json()["error"]["code"] == "profile_incomplete"
    unknown = await client.put("/me/profile", json=FULL | {"subject_ids": [str(uuid4())]}, headers=bearer(maria))
    assert unknown.json()["error"]["code"] == "unknown_subject"
    assert (await client.put("/me/profile", json=FULL, headers=bearer(student, ("student",)))).status_code == 403

    # Скрытый профиль видит только владелец.
    draft = (await client.put("/me/profile", json=FULL, headers=bearer(maria))).json()
    assert draft["missing"] == [] and draft["profile"]["published"] is False
    assert (await client.get(f"/tutors/{maria}")).status_code == 404
    assert (await client.get(f"/tutors/{maria}", headers=bearer(maria))).status_code == 200

    photo = fakes.file(maria)
    done = await publish(client, maria, photo_file_id=photo)
    assert done["profile"]["photo_url"] == f"http://s3/{photo}" and done["profile"]["share_url"].endswith(f"/tutors/{maria}")
    assert done["profile"]["subjects"] == [{"id": MATH, "name": "Математика"}]
    assert (await outbox("marketplace.profile.published"))[0]["data"]["user_id"] == str(maria)
    guest = (await client.get(f"/tutors/{maria}")).json()  # ссылка «Поделиться» — без входа
    assert guest["full_name"] == "Мария Иванова" and guest["about"].startswith("Готовлю")
    foreign_photo = fakes.file(uuid4())
    assert (await client.put("/me/profile", json=FULL | {"photo_file_id": foreign_photo}, headers=bearer(maria))).status_code == 422


async def test_search_filters_and_presence(client, fakes):
    a, b, c = uuid4(), uuid4(), uuid4()
    await person(a, "Анна Петрова")
    await person(b, "Борис Сидоров")
    await publish(client, a)
    await publish(client, b, subject_ids=[PHYSICS], levels=["student", "adult"], formats=["individual"], price=3000,
                  headline="Физика для студентов и взрослых")
    await client.put("/me/profile", json=FULL, headers=bearer(c))  # не опубликован — в поиске нет
    fakes.online(a, minutes_ago=2)
    fakes.online(b, minutes_ago=300)

    def names(r):
        return [t["full_name"] for t in r.json()["items"]]

    assert sorted(names(await client.get("/tutors"))) == ["Анна Петрова", "Борис Сидоров"]
    assert names(await client.get("/tutors", params={"subject_id": PHYSICS})) == ["Борис Сидоров"]
    assert names(await client.get("/tutors", params={"level": "10-11"})) == ["Анна Петрова"]
    assert names(await client.get("/tutors", params={"format": "group"})) == ["Анна Петрова"]
    assert names(await client.get("/tutors", params={"price_max": 2000})) == ["Анна Петрова"]
    assert names(await client.get("/tutors", params={"price_min": 2000})) == ["Борис Сидоров"]
    assert names(await client.get("/tutors", params={"sort": "price_desc"})) == ["Борис Сидоров", "Анна Петрова"]
    assert names(await client.get("/tutors", params={"q": "студент"})) == ["Борис Сидоров"]
    assert names(await client.get("/tutors", params={"q": "Петрова"})) == ["Анна Петрова"]
    assert names(await client.get("/tutors", params={"verified": True})) == []
    items = {t["full_name"]: t for t in (await client.get("/tutors")).json()["items"]}
    assert items["Анна Петрова"]["presence"]["online"] is True and items["Борис Сидоров"]["presence"]["online"] is False
    assert items["Борис Сидоров"]["presence"]["last_seen_at"] is not None


async def test_education_moderation_and_badge(client, fakes):
    maria, viewer = uuid4(), uuid4()
    await person(maria, "Мария Иванова")
    await publish(client, maria)
    diploma = fakes.file(maria, "диплом.pdf")
    mine = (await client.post("/me/education", json={"title": "Диплом учителя математики", "institution": "МПГУ", "year": 2012,
                                                     "file_id": diploma}, headers=bearer(maria))).json()
    [doc] = mine["education"]
    assert doc["status"] == "pending" and doc["filename"] == "диплом.pdf"
    sent = (await outbox("marketplace.education.submitted"))[0]["data"]
    assert sent["title"] == "Диплом учителя математики — Мария Иванова"

    # Модератор видит файл; учителям — нет.
    assert (await client.get(f"/moderation/education/{doc['id']}", headers=bearer(uuid4()))).status_code == 403
    for_mod = (await client.get(f"/moderation/education/{doc['id']}", headers=bearer(uuid4(), ("moderator",)))).json()
    assert for_mod["file_url"] == f"http://s3/{diploma}"

    await decide("education_doc", doc["id"], "approve")
    assert (await client.get("/tutors", params={"verified": True})).json()["total"] == 1
    guest = (await client.get(f"/tutors/{maria}")).json()
    assert guest["education_verified"] is True and guest["education"] == []  # гостю — только бейдж
    signed = (await client.get(f"/tutors/{maria}", headers=bearer(viewer, ("student",)))).json()
    assert [(e["title"], e["year"], e["file_url"], e["status"]) for e in signed["education"]] == [
        ("Диплом учителя математики", 2012, None, None)]
    assert (await outbox("marketplace.education.approved"))[0]["data"]["user_id"] == str(maria)

    # Отклонённый документ: причина видна владельцу. Удаление последнего одобренного снимает бейдж.
    course = fakes.file(maria, "курс.jpg")
    mine = (await client.post("/me/education", json={"title": "Курс", "institution": "Фоксфорд", "year": 2020, "file_id": course},
                              headers=bearer(maria))).json()
    pending = next(d for d in mine["education"] if d["status"] == "pending")
    await decide("education_doc", pending["id"], "reject", "Не видно печати")
    mine = (await client.get("/me/profile", headers=bearer(maria))).json()
    assert next(d for d in mine["education"] if d["id"] == pending["id"])["comment"] == "Не видно печати"
    after = (await client.delete(f"/me/education/{doc['id']}", headers=bearer(maria))).json()
    assert after["profile"]["education_verified"] is False


async def test_admin_hides_profile(client):
    maria, boss = uuid4(), uuid4()
    await person(maria, "Мария Иванова")
    await publish(client, maria)
    hidden = await client.post(f"/admin/tutors/{maria}/hide", json={"reason": "Контакты в описании"}, headers=bearer(boss, ("admin",)))
    assert hidden.json()["published"] is False and hidden.json()["blocked_reason"] == "Контакты в описании"
    assert (await client.get(f"/tutors/{maria}")).status_code == 404
    assert (await client.get("/tutors")).json()["total"] == 0
    # Педагог видит причину, включить показ не может.
    mine = (await client.get("/me/profile", headers=bearer(maria))).json()
    assert mine["blocked_reason"] == "Контакты в описании"
    again = await client.put("/me/profile", json=FULL | {"published": True}, headers=bearer(maria))
    assert again.json()["error"]["code"] == "profile_blocked"
    assert (await client.post(f"/admin/tutors/{maria}/unhide", headers=bearer(boss, ("admin",)))).json()["blocked_reason"] is None
    await publish(client, maria)
    assert (await client.get(f"/tutors/{maria}")).status_code == 200


async def test_search_by_ids_only_published(client):
    a, b, hidden = uuid4(), uuid4(), uuid4()
    for u, n in ((a, "Анна"), (b, "Борис"), (hidden, "Скрытый")):
        await person(u, n)
    await publish(client, a)
    await publish(client, b)
    await client.put("/me/profile", json=FULL, headers=bearer(hidden))  # не опубликован
    found = (await client.get("/tutors", params={"ids": [str(a), str(hidden)]})).json()
    assert [t["full_name"] for t in found["items"]] == ["Анна"]
