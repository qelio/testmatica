from uuid import uuid4

from app import handlers, rubric
from app.deps import db

from .conftest import CHOICE, CODE, apply, bearer, link, run_code_checks, student

SUBJECTS = [{"id": str(uuid4()), "name": "Информатика"}]


async def catalog(client, user):
    async with db.sessionmaker() as s, s.begin():
        rubric.seed_exams(s, SUBJECTS)
    exams = (await client.get("/exams", headers=bearer(user))).json()
    return {e["title"]: e for e in exams}


async def make_task(client, owner, body, *items):
    resp = await client.post("/tasks", json=body | {"exam_item_ids": [i["id"] for i in items]}, headers=bearer(owner))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def solve(client, task, pupil, **answer):
    resp = await client.post(f"/tasks/{task['id']}/submissions",
                             json={"context_type": "practice", "context_id": str(uuid4()), "answer": answer}, headers=student(pupil))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_catalog_and_task_tags(client):
    teacher = uuid4()
    exams = await catalog(client, teacher)
    ege = exams["ЕГЭ · Информатика"]
    assert ege["kind"] == "ege" and len(ege["items"]) == 27 and ege["items"][1]["title"] == "Таблицы истинности"
    assert len(exams["ОГЭ · Информатика"]["items"]) == 15

    task = await make_task(client, teacher, CHOICE, ege["items"][1], exams["ОГЭ · Информатика"]["items"][2])
    assert [e["label"] for e in task["exam_items"]] == ["ЕГЭ №2", "ОГЭ №3"]
    found = (await client.get("/tasks", params={"scope": "mine", "exam_item_id": ege["items"][1]["id"]}, headers=bearer(teacher))).json()
    assert found["total"] == 1 and found["items"][0]["exam_items"][0]["title"] == "Таблицы истинности"
    bad = await client.post("/tasks", json=CHOICE | {"exam_item_ids": [str(uuid4())]}, headers=bearer(teacher))
    assert bad.json()["error"]["code"] == "exam_item_not_found"

    # Задание с привязанными задачами не удалить; номер не дублируется.
    mod = bearer(uuid4(), ("moderator",))
    assert (await client.delete(f"/exam-items/{ege['items'][1]['id']}", headers=mod)).status_code == 409
    dup = await client.post(f"/exams/{ege['id']}/items", json={"number": 5, "title": "x"}, headers=mod)
    assert dup.json()["error"]["code"] == "number_taken"
    added = await client.post(f"/exams/{ege['id']}/items", json={"number": 28, "title": "Новое задание"}, headers=mod)
    assert added.status_code == 201
    assert (await client.patch(f"/exam-items/{added.json()['id']}", json={"title": "Переименовано"}, headers=mod)).json()["title"] == "Переименовано"
    assert (await client.delete(f"/exam-items/{added.json()['id']}", headers=mod)).status_code == 204
    assert (await client.post(f"/exams/{ege['id']}/items", json={"number": 29, "title": "x"}, headers=bearer(teacher))).status_code == 403


async def test_student_board_progress_and_marks(client):
    teacher, pupil, stranger = uuid4(), uuid4(), uuid4()
    await apply(handlers.on_identity_event, "identity.user.registered", user_id=pupil, full_name="Оля Смирнова", login=None)
    await link(teacher, pupil)
    ege = (await catalog(client, teacher))["ЕГЭ · Информатика"]
    n2, n24 = ege["items"][1], ege["items"][23]

    choice = await make_task(client, teacher, CHOICE, n2)
    other = await make_task(client, teacher, CHOICE | {"title": "Ещё одна"}, n2)
    code = await make_task(client, teacher, CODE, n24)
    right = next(o["id"] for o in choice["options"] if o["is_correct"])
    wrong = next(o["id"] for o in choice["options"] if not o["is_correct"])
    await solve(client, choice, pupil, option_ids=[wrong])
    await solve(client, choice, pupil, option_ids=[right])
    await solve(client, other, pupil, option_ids=[next(o["id"] for o in other["options"] if not o["is_correct"])])
    await solve(client, code, pupil, code="print(1)")  # неверно
    await solve(client, code, pupil, code="correct")
    await run_code_checks()

    params = {"exam_id": ege["id"], "target_type": "student", "target_id": str(pupil)}
    board = (await client.get("/exam-board", params=params, headers=bearer(teacher))).json()
    rows = {r["number"]: r for r in board["rows"]}
    assert board["can_edit"] and board["students"] == [{"id": str(pupil), "full_name": "Оля Смирнова"}]
    assert {k: rows[2]["progress"][k] for k in ("attempted", "solved", "attempts", "correct_attempts")} == {
        "attempted": 2, "solved": 1, "attempts": 3, "correct_attempts": 1}
    assert rows[24]["progress"]["solved"] == 1 and rows[1]["progress"]["attempts"] == 0

    # Отметки педагога: «пройдено» и примечание; дата не сдвигается при правке примечания.
    mark = {"target_type": "student", "target_id": str(pupil), "item_id": n2["id"], "done": True, "note": "Повторить"}
    assert (await client.put("/exam-marks", json=mark, headers=bearer(teacher))).status_code == 204
    first = (await client.get("/exam-board", params=params, headers=bearer(teacher))).json()["rows"][1]
    await client.put("/exam-marks", json=mark | {"note": "Разобрали"}, headers=bearer(teacher))
    second = (await client.get("/exam-board", params=params, headers=bearer(teacher))).json()["rows"][1]
    assert second["done"] and second["note"] == "Разобрали" and second["done_at"] == first["done_at"]

    # Ученик видит свой прогресс и отметки, но не примечания и не может отмечать.
    own = (await client.get("/exam-board", params=params, headers=student(pupil))).json()
    assert own["can_edit"] is False and own["rows"][1]["done"] and own["rows"][1]["note"] is None
    assert (await client.put("/exam-marks", json=mark, headers=student(pupil))).status_code == 403
    # Чужой педагог — нет доступа.
    assert (await client.get("/exam-board", params=params, headers=bearer(stranger))).status_code == 404

    # Разбор по задачам задания.
    tasks = (await client.get("/exam-board/tasks", params={"student_id": str(pupil), "item_id": n2["id"]}, headers=bearer(teacher))).json()
    assert {(t["title"], t["attempts"], t["solved"], t["last_status"]) for t in tasks} == {
        ("Корень уравнения", 2, True, "correct"), ("Ещё одна", 1, False, "incorrect")}


async def test_group_board(client, fakes):
    teacher, a, b = uuid4(), uuid4(), uuid4()
    group = str(uuid4())
    fakes.groups[group] = {"id": group, "teacher_id": str(teacher), "member_ids": [str(a), str(b)]}
    ege = (await catalog(client, teacher))["ЕГЭ · Информатика"]
    task = await make_task(client, teacher, CHOICE, ege["items"][0])
    right = next(o["id"] for o in task["options"] if o["is_correct"])
    await link(teacher, a)
    await link(teacher, b)
    await solve(client, task, a, option_ids=[right])
    await solve(client, task, b, option_ids=[right])

    params = {"exam_id": ege["id"], "target_type": "group", "target_id": group}
    board = (await client.get("/exam-board", params=params, headers=bearer(teacher))).json()
    row = board["rows"][0]
    assert row["progress"]["solved"] == 2 and len(row["by_student"]) == 2 and len(board["students"]) == 2
    mark = {"target_type": "group", "target_id": group, "item_id": ege["items"][0]["id"], "done": True}
    assert (await client.put("/exam-marks", json=mark, headers=bearer(teacher))).status_code == 204
    assert (await client.get("/exam-board", params=params, headers=bearer(teacher))).json()["rows"][0]["done"] is True
    # Чужая группа.
    assert (await client.get("/exam-board", params=params, headers=bearer(uuid4()))).status_code == 404
