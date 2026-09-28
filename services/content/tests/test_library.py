from uuid import uuid4

import pytest

from app import handlers

from .conftest import apply, bearer, link, outbox, student

MOD = ("moderator",)


async def subject_id(client, name="Алгебра"):
    return next(s["id"] for s in (await client.get("/subjects")).json() if s["name"] == name)


async def build_course(client, teacher, title="Линейные уравнения", with_subject=True):
    """Курс → раздел → два модуля, в первом — текст с формулой и ссылка."""
    body = {"title": title, "description": "7 класс"}
    if with_subject:
        body["subject_id"] = await subject_id(client)
    course = (await client.post("/courses", json=body, headers=bearer(teacher))).json()
    tree = (await client.post(f"/nodes/{course['id']}/children", json={"title": "Основы"}, headers=bearer(teacher))).json()
    section = tree["sections"][0]["id"]
    for t in ("Что такое уравнение", "Решение уравнений"):
        tree = (await client.post(f"/nodes/{section}/children", json={"title": t}, headers=bearer(teacher))).json()
    m1, m2 = (m["id"] for m in tree["sections"][0]["modules"])
    text = await client.post(
        f"/modules/{m1}/materials",
        json={"kind": "text", "title": "Определение", "body": "Уравнение — равенство с неизвестным: $ax + b = 0$"},
        headers=bearer(teacher),
    )
    assert text.status_code == 201, text.text
    link_m = await client.post(
        f"/modules/{m1}/materials", json={"kind": "link", "title": "Видеоурок", "url": "https://youtu.be/abc"}, headers=bearer(teacher)
    )
    assert link_m.status_code == 201
    return course["id"], section, m1, m2, text.json()["id"], link_m.json()["id"]


async def test_build_tree_and_reorder(client):
    t = uuid4()
    course_id, section, m1, m2, text_id, link_id = await build_course(client, t)
    tree = (await client.get(f"/courses/{course_id}", headers=bearer(t))).json()
    assert tree["status"] == "private" and tree["can_edit"] is True
    assert tree["subject"]["name"] == "Алгебра"
    assert [m["title"] for m in tree["sections"][0]["modules"]] == ["Что такое уравнение", "Решение уравнений"]
    assert [x["title"] for x in tree["sections"][0]["modules"][0]["materials"]] == ["Определение", "Видеоурок"]
    assert (tree["sections_count"], tree["materials_count"]) == (1, 2)

    await client.post(f"/nodes/{m2}/move", json={"direction": "up"}, headers=bearer(t))
    await client.post(f"/materials/{link_id}/move", json={"direction": "up"}, headers=bearer(t))
    tree = (await client.get(f"/courses/{course_id}", headers=bearer(t))).json()
    assert [m["title"] for m in tree["sections"][0]["modules"]] == ["Решение уравнений", "Что такое уравнение"]
    assert [x["title"] for x in tree["sections"][0]["modules"][1]["materials"]] == ["Видеоурок", "Определение"]

    # Иерархия строгая: в модуль нельзя добавить раздел, материал — только в модуль.
    assert (await client.post(f"/nodes/{m1}/children", json={"title": "x"}, headers=bearer(t))).status_code == 422
    bad = await client.post(f"/modules/{section}/materials", json={"kind": "text", "title": "x", "body": "y"}, headers=bearer(t))
    assert bad.status_code == 422
    empty = await client.post(f"/modules/{m1}/materials", json={"kind": "text", "title": "x", "body": "  "}, headers=bearer(t))
    assert empty.status_code == 422

    assert (await client.delete(f"/nodes/{section}", headers=bearer(t))).status_code == 204
    tree = (await client.get(f"/courses/{course_id}", headers=bearer(t))).json()
    assert tree["sections"] == [] and tree["materials_count"] == 0


async def test_private_library_visibility(client):
    t, pupil, stranger = uuid4(), uuid4(), uuid4()
    course_id, _, m1, *_ = await build_course(client, t)

    assert (await client.get(f"/courses/{course_id}")).status_code == 404  # гость
    assert (await client.get(f"/courses/{course_id}", headers=student(stranger))).status_code == 404
    assert (await client.get(f"/courses/{course_id}", headers=student(pupil))).status_code == 404

    await link(t, pupil)
    seen = (await client.get(f"/courses/{course_id}", headers=student(pupil))).json()
    assert seen["title"] == "Линейные уравнения" and seen["can_edit"] is False
    assert [c["id"] for c in (await client.get("/shared/courses", headers=student(pupil))).json()] == [course_id]
    # Ученик только читает.
    assert (await client.post(f"/nodes/{course_id}/children", json={"title": "x"}, headers=student(pupil))).status_code == 403

    await apply(handlers.on_classroom_event, "classroom.link.ended", teacher_id=t, student_id=pupil, link_id=uuid4())
    assert (await client.get(f"/modules/{m1}", headers=student(pupil))).status_code == 404


async def test_moderation_flow(client):
    t, moderator = uuid4(), uuid4()
    course_id, _, m1, *_ = await build_course(client, t)

    submitted = await client.post(f"/courses/{course_id}/submit", headers=bearer(t))
    assert submitted.json()["status"] == "pending"
    assert (await outbox("content.course.submitted"))[0]["data"]["materials_count"] == 2
    # На проверке курс заблокирован.
    locked = await client.post(f"/nodes/{course_id}/children", json={"title": "x"}, headers=bearer(t))
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "course_pending"
    assert (await client.get(f"/moderation/courses/{course_id}", headers=bearer(moderator, MOD))).status_code == 200

    decision = {"kind": "course", "ref_id": course_id, "author_id": str(t), "moderator_id": str(moderator)}
    await apply(handlers.on_moderation_decision, "moderation.decision.made", **decision, decision="reject", comment="Добавьте примеры")
    rejected = (await client.get(f"/courses/{course_id}", headers=bearer(t))).json()
    assert (rejected["status"], rejected["review_comment"], rejected["can_edit"]) == ("rejected", "Добавьте примеры", True)
    assert (await outbox("content.course.rejected"))[0]["data"]["comment"] == "Добавьте примеры"

    await client.post(f"/modules/{m1}/materials", json={"kind": "card", "title": "Пример", "body": "$2x=4$, $x=2$"}, headers=bearer(t))
    assert (await client.post(f"/courses/{course_id}/submit", headers=bearer(t))).json()["status"] == "pending"
    await apply(handlers.on_moderation_decision, "moderation.decision.made", **decision, decision="approve", comment=None)

    # Опубликованный курс виден гостям и есть в каталоге.
    guest = await client.get(f"/courses/{course_id}")
    assert guest.status_code == 200 and guest.json()["status"] == "published" and guest.json()["can_edit"] is False
    catalog = (await client.get("/catalog", params={"subject_id": await subject_id(client)})).json()
    assert [c["id"] for c in catalog] == [course_id]
    assert (await client.get("/catalog", params={"q": "линейн"})).json()[0]["id"] == course_id
    assert (await client.get("/catalog", params={"q": "химия"})).json() == []
    # Автор-педагог больше не правит опубликованный курс.
    assert (await client.patch(f"/nodes/{course_id}", json={"title": "x"}, headers=bearer(t))).status_code == 403

    # Снять с публикации — курс возвращается в приватную библиотеку.
    assert (await client.post(f"/courses/{course_id}/unpublish", headers=bearer(t))).json()["status"] == "private"
    assert (await client.get(f"/courses/{course_id}")).status_code == 404


async def test_submit_requirements_and_staff_publish(client):
    t = uuid4()
    course_id, *_ = await build_course(client, t, with_subject=False)
    no_subject = await client.post(f"/courses/{course_id}/submit", headers=bearer(t))
    assert no_subject.json()["error"]["code"] == "subject_required"
    empty = (await client.post("/courses", json={"title": "Пустой", "subject_id": await subject_id(client)}, headers=bearer(t))).json()
    assert (await client.post(f"/courses/{empty['id']}/submit", headers=bearer(t))).json()["error"]["code"] == "course_empty"

    editor = uuid4()
    staff_course, *_ = await build_course(client, editor, title="Курс редакции")
    published = await client.post(f"/courses/{staff_course}/submit", headers=bearer(editor, MOD))
    assert published.json()["status"] == "published"
    assert (await outbox("content.course.submitted")) == []


async def test_file_materials(client, fakes):
    t = uuid4()
    course_id, _, m1, *_ = await build_course(client, t)
    video = fakes.file(t, "урок.mp4", "video/mp4")
    pdf = fakes.file(t, "конспект.pdf", "application/pdf")
    foreign = fakes.file(uuid4(), "чужое.pdf", "application/pdf")

    ok = await client.post(f"/modules/{m1}/materials", json={"kind": "video", "title": "Разбор", "file_id": video}, headers=bearer(t))
    assert ok.status_code == 201 and ok.json()["file"]["url"] == f"http://s3/{video}"
    wrong = await client.post(f"/modules/{m1}/materials", json={"kind": "video", "title": "x", "file_id": pdf}, headers=bearer(t))
    assert wrong.json()["error"]["code"] == "invalid_file"
    stolen = await client.post(f"/modules/{m1}/materials", json={"kind": "pdf", "title": "x", "file_id": foreign}, headers=bearer(t))
    assert stolen.status_code == 422

    content = (await client.get(f"/modules/{m1}", headers=bearer(t))).json()
    assert [m["kind"] for m in content["materials"]] == ["text", "link", "video"]
    assert content["materials"][2]["file"]["filename"] == "урок.mp4"


async def test_progress_favorites_and_report(client, fakes):
    t, anya, petya = uuid4(), uuid4(), uuid4()
    course_id, _, m1, m2, text_id, link_id = await build_course(client, t)
    for s in (anya, petya):
        await link(t, s)
    await apply(handlers.on_identity_event, "identity.user.registered", user_id=anya, full_name="Аня", login=None)

    assert (await client.put(f"/materials/{text_id}/progress", json={}, headers=student(anya))).status_code == 204
    await client.put(f"/materials/{link_id}/progress", json={"position_sec": 125}, headers=student(anya))
    await client.put(f"/materials/{link_id}/favorite", headers=student(anya))

    tree = (await client.get(f"/courses/{course_id}", headers=student(anya))).json()
    assert tree["viewed_count"] == 2
    content = (await client.get(f"/modules/{m1}", headers=student(anya))).json()
    assert [(m["viewed"], m["position_sec"], m["favorite"]) for m in content["materials"]] == [(True, 0, False), (True, 125, True)]
    assert (content["prev_module_id"], content["next_module_id"]) == (None, m2)
    assert [f["id"] for f in (await client.get("/favorites", headers=student(anya))).json()] == [link_id]

    # Посторонний не может отметить материал из чужой приватной библиотеки.
    assert (await client.put(f"/materials/{text_id}/progress", json={}, headers=student(uuid4()))).status_code == 404

    gid = str(uuid4())
    fakes.groups[gid] = {"id": gid, "teacher_id": str(t), "member_ids": [str(anya), str(petya)]}
    report = (await client.get(f"/courses/{course_id}/progress", params={"group_id": gid}, headers=bearer(t))).json()
    assert [m["title"] for m in report["materials"]] == ["Определение", "Видеоурок"]
    rows = {r["full_name"]: sorted(r["viewed"]) for r in report["students"]}
    assert rows == {"Аня": sorted([text_id, link_id]), "Ученик": []}
    other = await client.get(f"/courses/{course_id}/progress", params={"group_id": gid}, headers=bearer(uuid4()))
    assert other.status_code == 404


@pytest.mark.parametrize("roles", [("student",)])
async def test_students_cannot_author(client, roles):
    resp = await client.post("/courses", json={"title": "Мой курс"}, headers=bearer(uuid4(), roles))
    assert resp.status_code == 403


async def test_course_constructor_with_tasks(client, fakes):
    t, other = uuid4(), uuid4()
    course_id, _, m1, *_ = await build_course(client, t)
    own = fakes.task(t, "Корень уравнения")
    manual = fakes.task(t, "Докажите", type_="long")
    foreign_private = fakes.task(other, "Чужая", status="private")
    foreign_public = fakes.task(other, "Из банка", type_="code", status="published")

    ok = await client.post(f"/modules/{m1}/materials", json={"kind": "task", "task_id": own}, headers=bearer(t))
    assert ok.status_code == 201, ok.text
    assert (ok.json()["kind"], ok.json()["title"], ok.json()["task_id"]) == ("task", "Корень уравнения", own)
    named = await client.post(f"/modules/{m1}/materials", json={"kind": "task", "task_id": foreign_public, "title": "Закрепление"}, headers=bearer(t))
    assert named.json()["title"] == "Закрепление"

    no_manual = await client.post(f"/modules/{m1}/materials", json={"kind": "task", "task_id": manual}, headers=bearer(t))
    assert no_manual.json()["error"]["code"] == "task_manual_check"
    no_foreign = await client.post(f"/modules/{m1}/materials", json={"kind": "task", "task_id": foreign_private}, headers=bearer(t))
    assert no_foreign.json()["error"]["code"] == "task_not_available"
    assert (await client.post(f"/modules/{m1}/materials", json={"kind": "task"}, headers=bearer(t))).status_code == 422

    kinds = [m["kind"] for m in (await client.get(f"/modules/{m1}", headers=bearer(t))).json()["materials"]]
    assert kinds == ["text", "link", "task", "task"]

    # Своя приватная задача уходит на проверку вместе с курсом, опубликованная чужая — нет.
    assert (await client.post(f"/courses/{course_id}/submit", headers=bearer(t))).json()["status"] == "pending"
    event = (await outbox("content.course.submitted"))[0]["data"]
    assert (event["task_ids"], event["tasks_count"]) == ([own], 2)


async def test_submit_fails_if_task_disappeared(client, fakes):
    t = uuid4()
    course_id, _, m1, *_ = await build_course(client, t)
    tid = fakes.task(t, "Временная")
    await client.post(f"/modules/{m1}/materials", json={"kind": "task", "task_id": tid}, headers=bearer(t))
    del fakes.tasks[tid]  # задачу удалили в банке
    resp = await client.post(f"/courses/{course_id}/submit", headers=bearer(t))
    assert resp.json()["error"]["code"] == "tasks_unavailable"


async def test_admin_removes_any_course(client):
    t, pupil, boss = uuid4(), uuid4(), uuid4()
    course_id, *_ = await build_course(client, t)
    await link(t, pupil)
    staff_course = (await client.post("/courses", json={"title": "Методичка"}, headers=bearer(boss, MOD))).json()
    assert (await client.post(f"/admin/courses/{staff_course['id']}/remove", json={"reason": "проверка"},
                              headers=bearer(boss, MOD))).status_code == 403  # модератору — нет, только администратору

    removed = await client.post(f"/admin/courses/{course_id}/remove", json={"reason": "Нарушение авторских прав"},
                                headers=bearer(boss, ("admin",)))
    assert removed.json()["status"] == "removed"
    event = (await outbox("content.course.removed"))[0]["data"]
    assert event["reason"] == "Нарушение авторских прав" and event["author_id"] == str(t)
    # Ученикам автора не видно, автор видит причину и не может править или отправить снова.
    assert (await client.get(f"/courses/{course_id}", headers=student(pupil))).status_code == 404
    own = (await client.get(f"/courses/{course_id}", headers=bearer(t))).json()
    assert own["review_comment"] == "Нарушение авторских прав" and own["can_edit"] is False
    assert (await client.post(f"/courses/{course_id}/submit", headers=bearer(t))).status_code in (403, 409)

    restored = await client.post(f"/admin/courses/{course_id}/restore", headers=bearer(boss, ("admin",)))
    assert restored.json()["status"] == "private" and restored.json()["review_comment"] is None  # был приватным
    assert (await client.get(f"/courses/{course_id}", headers=student(pupil))).status_code == 200
