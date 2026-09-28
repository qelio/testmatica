from datetime import date, datetime
from uuid import uuid4

from testmatica_common.testing import make_envelope

from app import moderation
from app.deps import db

from .conftest import add_person, bearer, outbox
from .test_journal import period

LESSONS = [
    {"topic": "Обыкновенные дроби", "goals": "Понимать запись дроби",
     "class_items": [{"kind": "module", "ref_id": str(uuid4()), "title": "Модуль: дроби"}],
     "home_items": [{"kind": "test", "ref_id": str(uuid4()), "title": "Тест: дроби"}]},
    {"topic": "Сложение дробей", "home_items": [{"kind": "link", "title": "Видео", "url": "https://example.com/v"}]},
    {"topic": "Вычитание дробей"},
]


async def make_template(client, owner, roles=("teacher",), **extra):
    resp = await client.post("/plan-templates", json={"title": "Дроби, 5 класс", "subject": "Математика", "level": "5 класс",
                                                      "lessons": LESSONS} | extra, headers=bearer(owner, roles))
    assert resp.status_code == 201, resp.text
    return resp.json()


def local_day(lesson_id, world) -> str:
    starts = datetime.fromisoformat(world.lessons[str(lesson_id)]["starts_at"])
    return starts.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Moscow")).date().isoformat()


async def test_templates_library_and_moderation(client):
    author, other, mod = uuid4(), uuid4(), uuid4()
    await add_person(author, "Мария Ивановна", ("teacher",))
    t = await make_template(client, author)
    assert t["lessons_count"] == 3 and t["can_edit"] and t["lessons"][0]["class_items"][0]["kind"] == "module"
    bad = await client.post("/plan-templates", json={"title": "X", "lessons": [{"topic": "Y", "home_items": [{"kind": "link", "title": "a", "url": "ftp://x"}]}]},
                            headers=bearer(author))
    assert bad.status_code == 422

    # Чужой приватный шаблон не виден; после публикации — виден и копируется («на основе чужого»).
    assert (await client.get(f"/plan-templates/{t['id']}", headers=bearer(other))).status_code == 404
    sub = (await client.post(f"/plan-templates/{t['id']}/submit", headers=bearer(author))).json()
    assert sub["status"] == "pending"
    assert (await outbox("academic.plan_template.submitted"))[0]["data"]["lessons_count"] == 3
    assert (await client.put(f"/plan-templates/{t['id']}", json={"title": "Z", "lessons": []}, headers=bearer(author))).status_code == 409

    async with db.sessionmaker() as s, s.begin():
        await moderation.on_moderation_decision(make_envelope("moderation.decision.made", {
            "kind": "plan_template", "ref_id": t["id"], "decision": "approve", "moderator_id": str(mod)}), s)
    public = (await client.get("/plan-templates", params={"scope": "public"}, headers=bearer(other))).json()
    assert [(x["title"], x["author_name"]) for x in public] == [("Дроби, 5 класс", "Мария Ивановна")]
    copy = (await client.post(f"/plan-templates/{t['id']}/copy", headers=bearer(other))).json()
    assert copy["owner_id"] == str(other) and copy["based_on_id"] == t["id"] and copy["status"] == "private" and copy["can_edit"]

    # Методист (модератор) публикует сразу.
    staff = await make_template(client, mod, ("moderator",), title="Геометрия")
    assert (await client.post(f"/plan-templates/{staff['id']}/submit", headers=bearer(mod, ("moderator",)))).json()["status"] == "published"


async def test_plan_from_template_with_dates(client, world):
    teacher, pupil = uuid4(), uuid4()
    group = world.group(teacher, [pupil])
    past = world.lesson(teacher, [pupil], days=-3, group_id=group)
    slots = [world.lesson(teacher, [pupil], days=d, group_id=group) for d in (1, 3, 8)]
    world.lesson(teacher, [pupil], days=5, group_id=group, status="cancelled")
    t = await make_template(client, teacher)

    plan = (await client.post("/plans", json={"target_type": "group", "target_id": str(group), "template_id": t["id"],
                                             "start_date": date.today().isoformat()}, headers=bearer(teacher))).json()
    assert plan["title"] == "Дроби, 5 класс" and plan["target_title"] == "7А"
    # Уроки легли на ближайшие занятия подряд; отменённое и прошедшее пропущены.
    assert [x["schedule_lesson_id"] for x in plan["lessons"]] == [str(s) for s in slots]
    assert plan["lessons"][0]["planned_date"] == local_day(slots[0], world)
    assert str(past) not in [s["id"] for s in plan["slots"]]

    # Постепенно: добавить урок после первого; изменить; отметить пройденным.
    added = (await client.post(f"/plans/{plan['id']}/lessons", params={"after": plan["lessons"][0]["id"]},
                               json={"topic": "Приведение к общему знаменателю"}, headers=bearer(teacher))).json()
    assert added["position"] == 1 and added["planned_date"] is None
    first = plan["lessons"][0]
    done = await client.patch(f"/plans/{plan['id']}/lessons/{first['id']}", json={"done": True, "goals": "Готово"}, headers=bearer(teacher))
    assert done.json()["done"] and done.json()["goals"] == "Готово"

    # «Проставить даты» заново: пройденный урок остаётся на месте, остальные сдвигаются; последнему занятий не хватило.
    res = (await client.post(f"/plans/{plan['id']}/distribute", json={}, headers=bearer(teacher))).json()
    assert res == {"placed": 2, "left": 1}
    lessons = (await client.get(f"/plans/{plan['id']}", headers=bearer(teacher))).json()["lessons"]
    assert [(x["topic"], x["schedule_lesson_id"]) for x in lessons] == [
        ("Обыкновенные дроби", str(slots[0])),
        ("Приведение к общему знаменателю", str(slots[1])),
        ("Сложение дробей", str(slots[2])),
        ("Вычитание дробей", None),
    ]

    # К одному занятию — несколько уроков КТП; занятие чужой группы — нельзя.
    last = lessons[3]
    linked = await client.patch(f"/plans/{plan['id']}/lessons/{last['id']}", json={"schedule_lesson_id": str(slots[2])}, headers=bearer(teacher))
    assert linked.json()["planned_date"] == local_day(slots[2], world)
    other_group = world.group(teacher, [])
    foreign = world.lesson(teacher, [], days=2, group_id=other_group)
    wrong = await client.patch(f"/plans/{plan['id']}/lessons/{last['id']}", json={"schedule_lesson_id": str(foreign)}, headers=bearer(teacher))
    assert wrong.json()["error"]["code"] == "slot_mismatch"
    on_lesson = (await client.get(f"/ktp/by-lesson/{slots[2]}", headers=bearer(teacher))).json()
    assert [x["lesson"]["topic"] for x in on_lesson] == ["Сложение дробей", "Вычитание дробей"]

    # Темы КТП видны в журнале.
    j = (await client.get("/journal", params={"group_id": str(group), **period()}, headers=bearer(teacher))).json()
    assert next(x for x in j["lessons"] if x["id"] == str(slots[2]))["ktp"] == ["Сложение дробей", "Вычитание дробей"]

    # Перестановка и удаление.
    moved = (await client.post(f"/plans/{plan['id']}/lessons/{last['id']}/move", params={"to": 0}, headers=bearer(teacher))).json()
    assert moved["lessons"][0]["topic"] == "Вычитание дробей"
    assert (await client.delete(f"/plans/{plan['id']}/lessons/{last['id']}", headers=bearer(teacher))).status_code == 204
    summary = (await client.get("/plans", params={"target_id": str(group)}, headers=bearer(teacher))).json()
    assert summary[0]["lessons_count"] == 4 - 1 + 0 and summary[0]["done_count"] == 1 and summary[0]["next_topic"] == "Приведение к общему знаменателю"

    # Чужой педагог не видит план.
    assert (await client.get(f"/plans/{plan['id']}", headers=bearer(uuid4()))).status_code == 404


async def test_plan_from_scratch_and_save_as_template(client, world):
    teacher, pupil = uuid4(), uuid4()
    await add_person(pupil, "Оля Смирнова")
    world.links.add((str(teacher), str(pupil)))
    lesson = world.lesson(teacher, [pupil], days=2, student_id=pupil)
    plan = (await client.post("/plans", json={"target_type": "student", "target_id": str(pupil), "title": "Подготовка к ОГЭ"},
                              headers=bearer(teacher))).json()
    assert plan["lessons"] == [] and plan["target_title"] == "Оля Смирнова" and [s["id"] for s in plan["slots"]] == [str(lesson)]
    for topic in ("Задание 1", "Задание 2"):
        await client.post(f"/plans/{plan['id']}/lessons", json={"topic": topic}, headers=bearer(teacher))
    t = (await client.post(f"/plans/{plan['id']}/save-as-template", headers=bearer(teacher))).json()
    assert t["title"] == "Подготовка к ОГЭ" and [x["topic"] for x in t["lessons"]] == ["Задание 1", "Задание 2"]
    # Чужого ученика — нельзя.
    assert (await client.post("/plans", json={"target_type": "student", "target_id": str(uuid4())}, headers=bearer(teacher))).status_code == 404


async def test_admin_removes_template(client):
    methodist, teacher, boss = uuid4(), uuid4(), uuid4()
    t = await make_template(client, methodist, roles=("moderator",))
    published = (await client.post(f"/plan-templates/{t['id']}/submit", headers=bearer(methodist, ("moderator",)))).json()
    assert published["status"] == "published"
    assert (await client.post(f"/admin/plan-templates/{t['id']}/remove", json={"reason": "Устарел"},
                              headers=bearer(methodist, ("moderator",)))).status_code == 403
    removed = (await client.post(f"/admin/plan-templates/{t['id']}/remove", json={"reason": "Устарел"}, headers=bearer(boss, ("admin",)))).json()
    assert removed["status"] == "removed" and removed["review_comment"] == "Устарел"
    assert (await outbox("academic.plan_template.removed"))[0]["data"]["reason"] == "Устарел"
    # Из публичной библиотеки пропал, копию сделать нельзя.
    public = (await client.get("/plan-templates", params={"scope": "public"}, headers=bearer(teacher))).json()
    assert all(x["id"] != t["id"] for x in public)
    assert (await client.post(f"/plan-templates/{t['id']}/copy", headers=bearer(teacher))).status_code == 404
    assert (await client.post(f"/plan-templates/{t['id']}/copy", headers=bearer(methodist))).json()["error"]["code"] == "template_removed"
    back = (await client.post(f"/admin/plan-templates/{t['id']}/restore", headers=bearer(boss, ("admin",)))).json()
    assert back["status"] == "published"  # отмена — прежний статус, снова в библиотеке
