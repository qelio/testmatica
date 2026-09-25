from uuid import uuid4

from app import handlers

from .conftest import apply, bearer, outbox


async def submit(course_id, author, title):
    await apply(handlers.on_content_event, "content.course.submitted", course_id=course_id, title=title, author_id=author, materials_count=3)


async def test_fifo_queue_and_decisions(client):
    author, moderator = uuid4(), uuid4()
    await apply(handlers.on_identity_event, "identity.user.registered", user_id=author, full_name="Мария Ивановна", login=None)
    first, second = uuid4(), uuid4()
    await submit(first, author, "Линейные уравнения")
    await submit(second, author, "Дроби")
    await submit(first, author, "Линейные уравнения")  # повторное событие — без дубля

    queue = (await client.get("/queue", headers=bearer(moderator))).json()
    assert [i["title"] for i in queue] == ["Линейные уравнения", "Дроби"]  # кто раньше — тот первый
    assert queue[0]["author_name"] == "Мария Ивановна" and queue[0]["kind_label"] == "Курс в публичную библиотеку"
    assert (await client.get("/queue/stats", headers=bearer(moderator))).json() == {"course": 2}

    no_reason = await client.post(f"/queue/{queue[0]['id']}/decide", json={"decision": "reject"}, headers=bearer(moderator))
    assert no_reason.status_code == 422
    rejected = await client.post(
        f"/queue/{queue[0]['id']}/decide", json={"decision": "reject", "comment": "Нет примеров"}, headers=bearer(moderator)
    )
    assert rejected.json()["status"] == "rejected"
    again = await client.post(f"/queue/{queue[0]['id']}/decide", json={"decision": "approve"}, headers=bearer(moderator))
    assert again.status_code == 409
    await client.post(f"/queue/{queue[1]['id']}/decide", json={"decision": "approve"}, headers=bearer(moderator))

    decisions = [e["data"] for e in await outbox("moderation.decision.made")]
    assert [(d["ref_id"], d["decision"], d["comment"]) for d in decisions] == [
        (str(first), "reject", "Нет примеров"),
        (str(second), "approve", None),
    ]
    assert (await client.get("/queue", headers=bearer(moderator))).json() == []
    history = (await client.get("/queue", params={"status": "rejected"}, headers=bearer(moderator))).json()
    assert [i["title"] for i in history] == ["Линейные уравнения"]

    # Исправленный курс снова попадает в очередь.
    await submit(first, author, "Линейные уравнения")
    assert len((await client.get("/queue", headers=bearer(moderator))).json()) == 1


async def test_withdrawn_course_leaves_queue(client):
    course = uuid4()
    await submit(course, uuid4(), "Курс")
    await apply(handlers.on_content_event, "content.course.unpublished", course_id=course, title="Курс", author_id=uuid4())
    assert (await client.get("/queue", headers=bearer(uuid4()))).json() == []


async def test_only_moderators(client):
    assert (await client.get("/queue", headers=bearer(uuid4(), ("teacher",)))).status_code == 403
    assert (await client.get("/queue", headers=bearer(uuid4(), ("admin",)))).status_code == 200


async def test_tasks_enter_queue(client):
    task, author = uuid4(), uuid4()
    await apply(handlers.on_assessment_event, "assessment.task.submitted", task_id=task, title="Сумма двух чисел", author_id=author, type="code")
    queue = (await client.get("/queue", headers=bearer(uuid4()))).json()
    assert [(i["kind"], i["kind_label"], i["details"]) for i in queue] == [("task", "Задача в публичный банк", {"type": "code"})]
    await apply(handlers.on_assessment_event, "assessment.task.unpublished", task_id=task, title="x", author_id=author)
    assert (await client.get("/queue", headers=bearer(uuid4()))).json() == []
