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


async def test_plan_templates_enter_queue(client):
    template, author = uuid4(), uuid4()
    await apply(handlers.on_academic_event, "academic.plan_template.submitted", template_id=template, title="Дроби, 5 класс",
                author_id=author, lessons_count=12, subject="Математика")
    queue = (await client.get("/queue", headers=bearer(uuid4()))).json()
    assert [(i["kind"], i["kind_label"], i["details"]["lessons_count"]) for i in queue] == [
        ("plan_template", "КТП в публичную библиотеку", 12)]
    await apply(handlers.on_academic_event, "academic.plan_template.unpublished", template_id=template, title="x", author_id=author)
    assert (await client.get("/queue", headers=bearer(uuid4()))).json() == []



async def test_education_docs_enter_queue(client):
    doc, author = uuid4(), uuid4()
    await apply(handlers.on_marketplace_event, "marketplace.education.submitted", doc_id=doc, user_id=author,
                title="Диплом — Мария Иванова", institution="МПГУ", year=2012)
    [item] = (await client.get("/queue", headers=bearer(uuid4()))).json()
    assert (item["kind"], item["kind_label"], item["details"]["institution"]) == ("education_doc", "Документ об образовании", "МПГУ")
    await apply(handlers.on_marketplace_event, "marketplace.education.withdrawn", doc_id=doc, user_id=author)
    assert (await client.get("/queue", headers=bearer(uuid4()))).json() == []


async def test_reviews_replies_and_disputes(client):
    review, student, tutor, moderator = uuid4(), uuid4(), uuid4(), uuid4()
    base = {"review_id": review, "tutor_id": tutor, "student_id": student, "tutor_name": "Мария Иванова",
            "student_name": "Оля Смирнова", "rating": 3}
    await apply(handlers.on_marketplace_event, "marketplace.review.submitted", **base, text="Скучно")
    # Правка до проверки — та же заявка с новым текстом.
    await apply(handlers.on_marketplace_event, "marketplace.review.submitted", **(base | {"rating": 4}), text="Скучновато")
    [item] = (await client.get("/queue", headers=bearer(moderator))).json()
    assert item["kind"] == "review" and item["title"] == "Отзыв о педагоге Мария Иванова: 4/10"
    assert item["details"]["text"] == "Скучновато" and item["author_id"] == str(student)
    await client.post(f"/queue/{item['id']}/decide", json={"decision": "approve"}, headers=bearer(moderator))
    assert (await outbox("moderation.decision.made"))[0]["data"]["kind"] == "review"

    await apply(handlers.on_marketplace_event, "marketplace.review.reply_submitted", **base, text="Спасибо", review_text="Скучновато")
    await apply(handlers.on_marketplace_event, "marketplace.review.disputed", **base, reason="Не была на занятиях",
                text="Скучновато", dispute_id=uuid4())
    kinds = {i["kind"]: i for i in (await client.get("/queue", headers=bearer(moderator))).json()}
    assert set(kinds) == {"review_reply", "review_dispute"} and kinds["review_dispute"]["author_id"] == str(tutor)
    assert kinds["review_dispute"]["details"]["reason"] == "Не была на занятиях"

    # Ученик переписал отзыв — старые ответ и спор снимаются с проверки, отзыв снова в очереди.
    await apply(handlers.on_marketplace_event, "marketplace.review.submitted", **base, text="Переписала отзыв")
    assert [i["kind"] for i in (await client.get("/queue", headers=bearer(moderator))).json()] == ["review"]
    await apply(handlers.on_marketplace_event, "marketplace.review.withdrawn", review_id=review, tutor_id=tutor)
    assert (await client.get("/queue", headers=bearer(moderator))).json() == []
