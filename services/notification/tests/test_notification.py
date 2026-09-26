from uuid import uuid4

import pytest
from testmatica_common.testing import make_envelope

from app import handlers
from app.templates import UnknownTemplate, render

from .conftest import bearer, consumer


def email_command(template="login", **params):
    return make_envelope(
        "notification.email.send",
        {"to": "u@example.com", "template": template, "params": {"name": "Аня", "code": "123456", "ttl_minutes": 10, **params}},
    )


async def test_email_command_sends_once(sent_emails):
    c = consumer("notification.email", handlers.on_email_command)
    command = email_command()

    assert await c.process(command) is True
    # Повторная доставка того же сообщения не отправляет второе письмо.
    assert await c.process(command) is False

    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == "u@example.com"
    assert "123456" in sent_emails[0]["subject"]
    assert "Аня" in sent_emails[0]["text"]


async def test_failed_send_is_not_marked_processed(monkeypatch):
    async def broken(*_):
        raise ConnectionError("smtp down")

    monkeypatch.setattr(handlers.mailer, "send_email", broken)
    c = consumer("notification.email", handlers.on_email_command)
    command = email_command()
    with pytest.raises(ConnectionError):
        await c.process(command)

    # После восстановления SMTP повторная попытка должна пройти.
    sent = []

    async def ok(to, *_):
        sent.append(to)

    monkeypatch.setattr(handlers.mailer, "send_email", ok)
    assert await c.process(command) is True
    assert sent == ["u@example.com"]


def test_html_is_escaped():
    _, _, html = render("login", {"name": "<script>", "code": "1", "ttl_minutes": 1})
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_unknown_template():
    with pytest.raises(UnknownTemplate):
        render("nope", {})


async def test_welcome_notification_and_api(client):
    user_id = uuid4()
    c = consumer("notification.identity", handlers.on_identity_event)
    await c.process(make_envelope("identity.user.email_verified", {"user_id": str(user_id)}))
    await c.process(make_envelope("identity.user.logged_in", {"user_id": str(user_id)}))

    resp = await client.get("/notifications", headers=bearer(user_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["unread"] == 1
    assert body["items"][0]["kind"] == "welcome"

    other = await client.get("/notifications", headers=bearer(uuid4()))
    assert other.json() == {"items": [], "unread": 0}

    nid = body["items"][0]["id"]
    assert (await client.post(f"/notifications/{nid}/read", headers=bearer(uuid4()))).status_code == 404
    assert (await client.post(f"/notifications/{nid}/read", headers=bearer(user_id))).status_code == 204
    assert (await client.get("/notifications", headers=bearer(user_id))).json()["unread"] == 0


async def test_api_requires_token(client):
    assert (await client.get("/notifications")).status_code == 401


def test_invitation_template():
    subject, text, _ = render(
        "invitation", {"teacher_name": "Мария Ивановна", "group_text": " в классе «7А»", "url": "http://x/invite/t", "ttl_days": 14}
    )
    assert subject == "Мария Ивановна приглашает вас в Тестматику"
    assert "заниматься в классе «7А»" in text and "http://x/invite/t" in text


async def test_link_request_notifies_student_and_acceptance_notifies_teacher(client):
    teacher, student = uuid4(), uuid4()
    c = consumer("notification.classroom", handlers.on_classroom_event)
    await c.process(
        make_envelope(
            "classroom.link.requested",
            {"link_id": str(uuid4()), "teacher_id": str(teacher), "student_id": str(student), "teacher_name": "Мария"},
        )
    )
    await c.process(
        make_envelope(
            "classroom.link.created",
            {"link_id": str(uuid4()), "teacher_id": str(teacher), "student_id": str(student), "source": "request", "student_name": "Петя"},
        )
    )
    # Ученик, созданный педагогом вручную, уведомления не порождает.
    await c.process(
        make_envelope(
            "classroom.link.created",
            {"link_id": str(uuid4()), "teacher_id": str(teacher), "student_id": str(uuid4()), "source": "manual", "student_name": "Вася"},
        )
    )
    student_items = (await client.get("/notifications", headers=bearer(student))).json()["items"]
    assert [n["kind"] for n in student_items] == ["link_request"]
    teacher_items = (await client.get("/notifications", headers=bearer(teacher, ["teacher"]))).json()["items"]
    assert [n["title"] for n in teacher_items] == ["Петя принял(а) ваш запрос"]


def schedule_event(type_, teacher, students, actor, **extra):
    data = {
        "lesson_ids": [str(uuid4())], "count": 1, "teacher_id": str(teacher), "teacher_name": "Мария Ивановна",
        "student_ids": [str(s) for s in students], "title": "Петя", "subject": "Физика", "paid": True,
        "kind": "individual", "starts_at": "2026-10-01T12:00:00+00:00", "ends_at": "2026-10-01T13:00:00+00:00",
    } | extra
    return make_envelope(type_, data, actor_id=actor)


async def test_schedule_notifications_skip_actor_and_label_by_role(client):
    teacher, student = uuid4(), uuid4()
    c = consumer("notification.schedule", handlers.on_schedule_event)
    await c.process(schedule_event("schedule.lesson.created", teacher, [student], teacher))
    await c.process(schedule_event("schedule.lesson.cancelled", teacher, [student], teacher, reason="Болею"))
    await c.process(schedule_event("schedule.lesson.reminder", teacher, [student], teacher, hours=2))

    student_items = (await client.get("/notifications", headers=bearer(student))).json()["items"]
    assert sorted(n["title"] for n in student_items) == [
        "Занятие отменено: Мария Ивановна",
        "Новое занятие: Мария Ивановна",
        "Через 2 ч занятие: Мария Ивановна",
    ]
    assert student_items[0]["payload"]["starts_at"] == "2026-10-01T12:00:00+00:00"

    # Педагог — автор создания и отмены, ему приходит только напоминание (с именем ученика).
    teacher_items = (await client.get("/notifications", headers=bearer(teacher, ["teacher"]))).json()["items"]
    assert [n["title"] for n in teacher_items] == ["Через 2 ч занятие: Петя"]


async def test_reschedule_request_notifies_other_side(client):
    teacher, student = uuid4(), uuid4()
    c = consumer("notification.schedule", handlers.on_schedule_event)
    await c.process(
        schedule_event(
            "schedule.reschedule.requested", teacher, [student], student,
            request_id=str(uuid4()), new_starts_at="2026-10-02T12:00:00+00:00", by_teacher=False,
        )
    )
    teacher_items = (await client.get("/notifications", headers=bearer(teacher, ["teacher"]))).json()["items"]
    assert teacher_items[0]["title"] == "Петя предлагает перенести занятие"
    assert teacher_items[0]["payload"]["new_starts_at"] == "2026-10-02T12:00:00+00:00"
    assert (await client.get("/notifications", headers=bearer(student))).json()["items"] == []


async def test_new_grade_notifies_student(client):
    student = uuid4()
    c = consumer("notification.academic", handlers.on_academic_event)
    data = {
        "grade_id": str(uuid4()), "teacher_id": str(uuid4()), "teacher_name": "Мария Ивановна", "student_id": str(student),
        "lesson_id": str(uuid4()), "lesson_starts_at": "2026-09-28T06:00:00+00:00", "subject": "Алгебра", "value": 5,
        "grade_type": "Контрольная работа", "comment": "Отлично",
    }
    await c.process(make_envelope("academic.grade.created", data))
    await c.process(make_envelope("academic.grade.updated", data))
    items = (await client.get("/notifications", headers=bearer(student))).json()["items"]
    assert [(n["title"], n["body"]) for n in items] == [("Новая оценка: 5 — Алгебра", "Контрольная работа. Отлично")]


async def test_inapp_command_coalesces_unread_chat_notifications(client):
    user = uuid4()
    c = consumer("notification.inapp", handlers.on_inapp_command)

    def command(body, key="chat:1"):
        return make_envelope(
            "notification.inapp.send",
            {"user_ids": [str(user)], "kind": "message", "title": "Новое сообщение: 7А", "body": body,
             "payload": {"conversation_id": "1"}, "coalesce_key": key},
        )

    await c.process(command("Петя: привет"))
    await c.process(command("Аня: как дела?"))
    items = (await client.get("/notifications", headers=bearer(user))).json()["items"]
    assert [(n["body"]) for n in items] == ["Аня: как дела?"]

    # После прочтения следующее сообщение — новое уведомление.
    await client.post(f"/notifications/{items[0]['id']}/read", headers=bearer(user))
    await c.process(command("Петя: ещё вопрос"))
    await c.process(command("Объявление", key=None))
    items = (await client.get("/notifications", headers=bearer(user))).json()["items"]
    assert len(items) == 3


async def test_course_decisions_notify_author(client):
    author = uuid4()
    c = consumer("notification.content", handlers.on_content_event)
    data = {"course_id": str(uuid4()), "title": "Дроби", "author_id": str(author)}
    await c.process(make_envelope("content.course.rejected", data | {"comment": "Нет примеров"}))
    await c.process(make_envelope("content.course.published", data, actor_id=uuid4()))
    # Сам опубликовал (штатный редактор) — уведомлять не нужно.
    await c.process(make_envelope("content.course.published", data, actor_id=author))
    items = (await client.get("/notifications", headers=bearer(author))).json()["items"]
    assert sorted((n["title"], n["body"]) for n in items) == [
        ("Курс «Дроби» не прошёл проверку", "Нет примеров"),
        ("Курс «Дроби» опубликован", "Курс прошёл проверку и появился в публичной библиотеке."),
    ]


async def test_task_and_review_notifications(client):
    author, pupil = uuid4(), uuid4()
    c = consumer("notification.assessment", handlers.on_assessment_event)
    await c.process(make_envelope("assessment.task.rejected", {"task_id": str(uuid4()), "title": "Сумма", "author_id": str(author), "comment": "Мало тестов"}))
    await c.process(make_envelope("assessment.submission.reviewed", {
        "submission_id": str(uuid4()), "task_id": str(uuid4()), "task_title": "Доказательство", "student_id": str(pupil),
        "score": 0.8, "comment": "Не хватает вывода", "context_type": "practice", "context_id": str(uuid4())}))
    assert (await client.get("/notifications", headers=bearer(author, ["teacher"]))).json()["items"][0]["body"] == "Мало тестов"
    assert (await client.get("/notifications", headers=bearer(pupil))).json()["items"][0]["title"] == "Педагог проверил решение: «Доказательство» — 80%"


async def test_assignment_notifications(client):
    a, b = uuid4(), uuid4()
    c = consumer("notification.assessment", handlers.on_assessment_event)
    aid = str(uuid4())
    await c.process(make_envelope("assessment.assignment.created", {
        "assignment_id": aid, "title": "Дроби", "kind": "homework", "teacher_id": str(uuid4()),
        "student_ids": [str(a), str(b)], "deadline": "2026-10-01T17:00:00+00:00", "lesson_id": None}))
    item = (await client.get("/notifications", headers=bearer(a))).json()["items"][0]
    assert (item["title"], item["payload"]["deadline"]) == ("Новое ДЗ: «Дроби»", "2026-10-01T17:00:00+00:00")
    graded = {"assignment_id": aid, "attempt_id": str(uuid4()), "student_id": str(b), "title": "Дроби", "percent": 83.3,
              "grade": 4, "to_journal": False}
    await c.process(make_envelope("assessment.attempt.graded", graded))
    await c.process(make_envelope("assessment.attempt.graded", graded | {"attempt_id": str(uuid4()), "to_journal": True}))
    titles = [n["title"] for n in (await client.get("/notifications", headers=bearer(b))).json()["items"]]
    assert sorted(titles) == ["Новое ДЗ: «Дроби»", "Работа проверена: «Дроби» — 83.3%, оценка 4"]
    # Ответ из работы, проверенный педагогом, — без отдельного уведомления.
    await c.process(make_envelope("assessment.submission.reviewed", {
        "submission_id": str(uuid4()), "task_id": str(uuid4()), "task_title": "X", "student_id": str(a), "score": 1,
        "comment": "", "context_type": "assignment", "context_id": str(uuid4())}))
    assert len((await client.get("/notifications", headers=bearer(a))).json()["items"]) == 1


async def test_plan_template_notifications(client):
    author = uuid4()
    c = consumer("notification.academic", handlers.on_academic_event)
    await c.process(make_envelope("academic.plan_template.rejected", {
        "template_id": str(uuid4()), "title": "Дроби", "author_id": str(author), "comment": "Нет результатов уроков"}))
    item = (await client.get("/notifications", headers=bearer(author, ["teacher"]))).json()["items"][0]
    assert (item["title"], item["body"]) == ("КТП «Дроби» не прошло проверку", "Нет результатов уроков")


async def test_recording_ready_notification(client):
    teacher, pupil = uuid4(), uuid4()
    c = consumer("notification.video", handlers.on_video_event)
    await c.process(make_envelope("video.recording.ready", {
        "recording_id": str(uuid4()), "lesson_id": str(uuid4()), "teacher_id": str(teacher), "viewer_ids": [str(pupil)],
        "title": "7А · Алгебра · 25.09.2026", "duration_s": 600}))
    for user in (teacher, pupil):
        items = (await client.get("/notifications", headers=bearer(user))).json()["items"]
        assert items[0]["title"] == "Запись занятия готова: 7А · Алгебра · 25.09.2026"
