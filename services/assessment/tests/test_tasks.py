from uuid import uuid4

from app import handlers

from .conftest import CHOICE, CODE, LONG, MULTI, SECTION, SHORT, SUBJECT, TOPIC, apply, bearer, link, outbox, student


async def create(client, owner, body, roles=("teacher",)):
    resp = await client.post("/tasks", json=body, headers=bearer(owner, roles))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_validation(client):
    t = uuid4()
    no_correct = CHOICE | {"options": [{"text": "1"}, {"text": "2"}]}
    assert (await client.post("/tasks", json=no_correct, headers=bearer(t))).status_code == 422
    assert (await client.post("/tasks", json=SHORT | {"answers": []}, headers=bearer(t))).status_code == 422
    assert (await client.post("/tasks", json=CODE | {"tests": []}, headers=bearer(t))).status_code == 422
    bad_regex = SHORT | {"answers": [{"mode": "regex", "value": "(("}]}
    assert (await client.post("/tasks", json=bad_regex, headers=bearer(t))).status_code == 422
    # Ученик не создаёт задачи.
    assert (await client.post("/tasks", json=CHOICE, headers=student(uuid4()))).status_code == 403


async def test_answer_key_visibility(client):
    owner, pupil, other = uuid4(), uuid4(), uuid4()
    task = await create(client, owner, CHOICE)
    assert task["tags"] == ["7 класс", "уравнения"] and task["can_edit"] is True
    assert [o["is_correct"] for o in task["options"]] == [True, False, False]

    # Чужой педагог и посторонний ученик не видят приватную задачу.
    assert (await client.get(f"/tasks/{task['id']}", headers=bearer(other))).status_code == 404
    assert (await client.get(f"/tasks/{task['id']}", headers=student(pupil))).status_code == 404
    # Ученик автора видит условие, но не ответы.
    await link(owner, pupil)
    seen = (await client.get(f"/tasks/{task['id']}", headers=student(pupil))).json()
    assert [o["is_correct"] for o in seen["options"]] == [None, None, None] and seen["explanation"] == ""

    # После публикации ключ видят все педагоги, гость — только условие.
    await client.post(f"/tasks/{task['id']}/submit", headers=bearer(owner, ("moderator",)))
    assert (await client.get(f"/tasks/{task['id']}", headers=bearer(other))).json()["options"][0]["is_correct"] is True
    guest = (await client.get(f"/tasks/{task['id']}")).json()
    assert guest["options"][0]["is_correct"] is None and guest["tests"] is None


async def test_search_bank(client):
    a, b = uuid4(), uuid4()
    for body in (CHOICE, SHORT | {"difficulty": 2}, CODE | {"difficulty": 3}, LONG):
        t = await create(client, a, body, ("moderator",))
        await client.post(f"/tasks/{t['id']}/submit", headers=bearer(a, ("moderator",)))
    await create(client, b, CHOICE | {"title": "Черновик"})

    public = (await client.get("/tasks", headers=bearer(b))).json()
    assert public["total"] == 4
    assert {i["title"] for i in (await client.get("/tasks", params={"auto_only": True}, headers=bearer(b))).json()["items"]} == {
        "Корень уравнения", "Десятичная дробь", "Сумма двух чисел"}
    assert (await client.get("/tasks", params={"type": "code"}, headers=bearer(b))).json()["items"][0]["title"] == "Сумма двух чисел"
    assert (await client.get("/tasks", params={"difficulty": 2}, headers=bearer(b))).json()["total"] == 1
    assert (await client.get("/tasks", params={"tag": "Уравнения"}, headers=bearer(b))).json()["total"] == 1
    assert (await client.get("/tasks", params={"q": "иррационален"}, headers=bearer(b))).json()["total"] == 1
    assert (await client.get("/tasks", params={"subject_id": str(uuid4())}, headers=bearer(b))).json()["total"] == 0
    mine = (await client.get("/tasks", params={"scope": "mine"}, headers=bearer(b))).json()
    assert [i["title"] for i in mine["items"]] == ["Черновик"] and mine["items"][0]["status"] == "private"


async def test_edit_lifecycle_and_moderation(client):
    owner, moderator = uuid4(), uuid4()
    task = await create(client, owner, SHORT)
    upd = await client.put(f"/tasks/{task['id']}", json=SHORT | {"title": "Дробь 7/2"}, headers=bearer(owner))
    assert upd.json()["title"] == "Дробь 7/2"

    no_topic = await create(client, owner, SHORT | {"topic_id": None})
    assert (await client.post(f"/tasks/{no_topic['id']}/submit", headers=bearer(owner))).json()["error"]["code"] == "topic_required"

    assert (await client.post(f"/tasks/{task['id']}/submit", headers=bearer(owner))).json()["status"] == "pending"
    assert (await outbox("assessment.task.submitted"))[0]["data"]["title"] == "Дробь 7/2"
    locked = await client.put(f"/tasks/{task['id']}", json=SHORT, headers=bearer(owner))
    assert locked.json()["error"]["code"] == "task_pending"

    await apply(handlers.on_moderation_decision, "moderation.decision.made", kind="task", ref_id=task["id"],
                decision="reject", comment="Добавьте разбор", moderator_id=moderator)
    rejected = (await client.get(f"/tasks/{task['id']}", headers=bearer(owner))).json()
    assert (rejected["status"], rejected["review_comment"]) == ("rejected", "Добавьте разбор")
    await client.post(f"/tasks/{task['id']}/submit", headers=bearer(owner))
    await apply(handlers.on_moderation_decision, "moderation.decision.made", kind="task", ref_id=task["id"],
                decision="approve", comment=None, moderator_id=moderator)
    assert (await client.get(f"/tasks/{task['id']}")).json()["status"] == "published"
    # Опубликованную задачу педагог не правит — только копирует.
    assert (await client.put(f"/tasks/{task['id']}", json=SHORT, headers=bearer(owner))).status_code == 403


async def test_copy_published_task(client):
    author, teacher = uuid4(), uuid4()
    task = await create(client, author, CODE, ("moderator",))
    assert (await client.post(f"/tasks/{task['id']}/copy", headers=bearer(teacher))).status_code == 404  # ещё приватная
    await client.post(f"/tasks/{task['id']}/submit", headers=bearer(author, ("moderator",)))
    copy = (await client.post(f"/tasks/{task['id']}/copy", headers=bearer(teacher))).json()
    assert copy["status"] == "private" and copy["owner_id"] == str(teacher) and copy["can_edit"] is True
    assert copy["tests"] == CODE["tests"]


async def test_tasks_move_with_course_moderation(client):
    """Приватные задачи курса уходят на проверку вместе с курсом и публикуются вместе с ним."""
    author = uuid4()
    t1 = await create(client, author, CHOICE)
    t2 = await create(client, author, SHORT)
    course = uuid4()
    await apply(handlers.on_content_event, "content.course.submitted", course_id=course, author_id=author,
                task_ids=[t1["id"], t2["id"]], title="Курс")
    assert (await client.get(f"/tasks/{t1['id']}", headers=bearer(author))).json()["status"] == "pending"
    await apply(handlers.on_content_event, "content.course.published", course_id=course, author_id=author, title="Курс")
    assert (await client.get(f"/tasks/{t1['id']}")).json()["status"] == "published"
    assert (await client.get(f"/tasks/{t2['id']}")).json()["status"] == "published"


async def test_internal_lookup(client):
    from testmatica_common.internal import INTERNAL_HEADER

    from app.config import settings

    owner, other = uuid4(), uuid4()
    mine = await create(client, owner, LONG)
    foreign = await create(client, other, CHOICE)
    resp = await client.post(
        "/internal/tasks/lookup", json={"task_ids": [mine["id"], foreign["id"]], "user_id": str(owner)},
        headers={INTERNAL_HEADER: settings.internal_token},
    )
    brief = {t["title"]: (t["usable"], t["auto_checked"]) for t in resp.json()}
    assert brief == {"Доказательство": (True, False), "Корень уравнения": (False, True)}
    assert SUBJECT  # предмет задаётся в content, здесь — только id


async def test_rubric(client):
    """Рубрикатор: модератор ведёт разделы и темы, задачи ищутся по разделу вместе с его темами."""
    teacher, moderator = uuid4(), uuid4()
    mod = bearer(moderator, ("moderator",))
    assert (await client.post("/topics", json={"parent_id": SECTION, "title": "X"}, headers=bearer(teacher))).status_code == 403
    quad = (await client.post("/topics", json={"parent_id": SECTION, "title": "  Квадратные   уравнения "}, headers=mod)).json()
    assert quad["title"] == "Квадратные уравнения" and quad["subject_id"] == SUBJECT and quad["position"] == 1
    deep = await client.post("/topics", json={"parent_id": TOPIC, "title": "Слишком глубоко"}, headers=mod)
    assert deep.json()["error"]["code"] == "too_deep"
    geo = (await client.post("/topics", json={"subject_id": str(uuid4()), "subject_name": "Геометрия", "title": "Треугольники"},
                             headers=mod)).json()
    assert geo["parent_id"] is None

    # Предмет задачи берётся из темы, путь показывается в карточке.
    task = await create(client, teacher, CHOICE | {"topic_id": quad["id"], "subject_id": None, "subject_name": None})
    assert task["subject_name"] == "Алгебра" and task["topic_path"] == ["Уравнения", "Квадратные уравнения"]
    await create(client, teacher, SHORT)  # в «Линейных уравнениях»
    await create(client, teacher, LONG | {"topic_id": None})

    mine = lambda **p: client.get("/tasks", params={"scope": "mine", **p}, headers=bearer(teacher))  # noqa: E731
    assert (await (mine(topic_id=SECTION))).json()["total"] == 2  # раздел — вместе с темами
    assert (await (mine(topic_id=quad["id"]))).json()["total"] == 1
    assert [i["title"] for i in (await mine(no_topic=True)).json()["items"]] == ["Доказательство"]
    counts = {t["title"]: t["count"] for t in (await client.get("/topics", params={"scope": "mine"}, headers=bearer(teacher))).json()}
    assert counts == {"Уравнения": 0, "Линейные уравнения": 1, "Квадратные уравнения": 1, "Треугольники": 0}
    assert all(t["count"] == 0 for t in (await client.get("/topics", headers=bearer(teacher))).json())  # публичных ещё нет

    # Непустые узлы не удаляются; пустые — да.
    assert (await client.delete(f"/topics/{SECTION}", headers=mod)).json()["error"]["code"] == "topic_not_empty"
    assert (await client.delete(f"/topics/{quad['id']}", headers=mod)).json()["error"]["code"] == "topic_not_empty"
    assert (await client.delete(f"/topics/{geo['id']}", headers=mod)).status_code == 204
    renamed = await client.patch(f"/topics/{quad['id']}", json={"title": "Квадратные", "position": 0}, headers=mod)
    assert renamed.json()["title"] == "Квадратные"

    # Перенос: автор — пока задача не отправлена, модератор — всегда.
    moved = await client.post(f"/tasks/{task['id']}/topic", json={"topic_id": TOPIC}, headers=bearer(teacher))
    assert moved.json()["topic_path"] == ["Уравнения", "Линейные уравнения"]
    await client.post(f"/tasks/{task['id']}/submit", headers=bearer(teacher))
    locked = await client.post(f"/tasks/{task['id']}/topic", json={"topic_id": quad["id"]}, headers=bearer(teacher))
    assert locked.json()["error"]["code"] == "task_locked"
    by_mod = await client.post(f"/tasks/{task['id']}/topic", json={"topic_id": quad["id"]}, headers=mod)
    assert by_mod.json()["topic_path"] == ["Уравнения", "Квадратные"]
    assert (await client.delete(f"/topics/{quad['id']}", headers=mod)).status_code == 409


async def test_default_rubric_seed():
    from app import rubric
    from app.deps import db

    async with db.sessionmaker() as s, s.begin():
        created = await rubric.seed(s, [{"id": str(uuid4()), "name": "Информатика"}, {"id": str(uuid4()), "name": "Неизвестный"}])
    assert created == 4 + sum(len(v) for v in rubric.DEFAULT_TOPICS["Информатика"].values())
