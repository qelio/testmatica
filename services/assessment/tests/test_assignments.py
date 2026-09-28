from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import update

from app import attempts
from app.deps import db
from app.models import Assignment, Attempt

from .conftest import CHOICE, CODE, LONG, SHORT, bearer, link, outbox, run_code_checks, student


async def make_tasks(client, teacher):
    out = []
    for body in (CHOICE, SHORT, CODE, LONG | {"file_mode": "optional"}):
        resp = await client.post("/tasks", json=body, headers=bearer(teacher))
        assert resp.status_code == 201, resp.text
        out.append(resp.json())
    return out


async def make_test(client, teacher, tasks, **settings):
    body = {"title": "Контрольная", "items": [{"task_id": t["id"], "points": p} for t, p in zip(tasks, (1, 1, 2, 2), strict=False)]}
    resp = await client.post("/tests", json=body | settings, headers=bearer(teacher))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def group_of(fakes, teacher, *pupils):
    gid = str(uuid4())
    fakes.groups[gid] = {"id": gid, "teacher_id": str(teacher), "title": "9Б", "member_ids": [str(p) for p in pupils]}
    for p in pupils:
        await link(teacher, p)
    return gid


async def assign(client, teacher, test, **body):
    resp = await client.post(f"/tests/{test['id']}/assign", json=body, headers=bearer(teacher))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def answer(client, attempt, task, pupil, **ans):
    resp = await client.put(f"/attempts/{attempt['id']}/answers/{task['id']}", json={"answer": ans}, headers=student(pupil))
    return resp


async def test_homework_full_cycle(client, fakes):
    teacher, olya, petya, stranger = uuid4(), uuid4(), uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    test = await make_test(client, teacher, tasks, shuffle_options=True)
    assert test["max_score"] == 6 and [i["points"] for i in test["items"]] == [1, 1, 2, 2]
    gid = await group_of(fakes, teacher, olya, petya)
    lesson = str(uuid4())
    fakes.lessons[lesson] = str(teacher)
    grade_type = str(uuid4())

    # Оценка в журнал — только с уроком и типом оценки.
    bad = await client.post(f"/tests/{test['id']}/assign", json={"target_type": "group", "target_id": gid, "grade_to_journal": True},
                            headers=bearer(teacher))
    assert bad.status_code == 422
    no_lesson = await client.post(f"/tests/{test['id']}/assign", json={"kind": "homework", "target_type": "group", "target_id": gid},
                                  headers=bearer(teacher))
    assert no_lesson.status_code == 422  # ДЗ — к уроку
    a = await assign(client, teacher, test, kind="homework", target_type="group", target_id=gid, lesson_id=lesson, grade_to_journal=True,
                     grade_type_id=grade_type, deadline=(datetime.now(UTC) + timedelta(days=2)).isoformat())
    assert a["target_title"] == "9Б" and len(a["students"]) == 2 and a["tasks_count"] == 4
    created = (await outbox("assessment.assignment.created"))[0]["data"]
    assert sorted(created["student_ids"]) == sorted([str(olya), str(petya)])

    # Ученик видит только своё; посторонний — ничего.
    mine = (await client.get("/assignments", headers=student(olya))).json()
    assert len(mine) == 1 and mine[0]["can_start"] and [s["student_id"] for s in mine[0]["students"]] == [str(olya)]
    assert (await client.get(f"/assignments/{a['id']}", headers=student(stranger))).status_code == 404

    attempt = (await client.post(f"/assignments/{a['id']}/start", headers=student(olya))).json()
    assert attempt["status"] == "in_progress" and len(attempt["tasks"]) == 4
    choice = next(t for t in attempt["tasks"] if t["task"]["type"] == "choice")
    assert all(o["is_correct"] is None for o in choice["task"]["options"])  # ключа нет
    again = (await client.post(f"/assignments/{a['id']}/start", headers=student(olya))).json()
    assert again["id"] == attempt["id"]  # вернулась к начатой

    by_type = {t["type"]: t for t in tasks}
    right = next(o["id"] for o in by_type["choice"]["options"] if o["is_correct"])
    assert (await answer(client, attempt, by_type["choice"], olya, option_ids=[right])).status_code == 200
    await answer(client, attempt, by_type["short"], olya, text="3,5")
    await answer(client, attempt, by_type["code"], olya, code="print('correct')")
    await answer(client, attempt, by_type["long"], olya, text="Решение")
    # Черновик можно менять до сдачи; прогресс виден педагогу.
    await answer(client, attempt, by_type["short"], olya, text="3.5")
    live = (await client.get(f"/assignments/{a['id']}", headers=bearer(teacher))).json()
    olya_row = next(s for s in live["students"] if s["student_id"] == str(olya))
    assert olya_row["attempts"][0]["answered"] == 4 and olya_row["attempts"][0]["status"] == "in_progress"

    done = (await client.post(f"/attempts/{attempt['id']}/submit", headers=student(olya))).json()
    assert done["status"] == "submitted" and done["checked"] is False and done["score"] is None
    assert (await client.post(f"/attempts/{attempt['id']}/submit", headers=student(olya))).status_code == 409
    assert (await answer(client, attempt, by_type["short"], olya, text="1")).status_code == 409
    no_retry = await client.post(f"/assignments/{a['id']}/start", headers=student(olya))
    assert no_retry.json()["error"]["code"] == "already_submitted"

    await run_code_checks()
    long_sub = next(t["result"] for t in (await client.get(f"/attempts/{attempt['id']}", headers=bearer(teacher))).json()["tasks"]
                    if t["task"]["type"] == "long")
    await client.post(f"/submissions/{long_sub['id']}/review", json={"score": 0.5, "comment": "Не хватает вывода"}, headers=bearer(teacher))

    result = (await client.get(f"/attempts/{attempt['id']}", headers=student(olya))).json()
    assert result["checked"] and result["score"] == 5 and result["percent"] == 83.3 and result["grade"] == 4
    assert [t["earned"] for t in result["tasks"] if t["task"]["type"] == "long"] == [1.0]
    assert all(t["task"]["explanation"] is not None for t in result["tasks"])
    graded = (await outbox("assessment.attempt.graded"))[-1]["data"]
    assert graded["grade"] == 4 and graded["to_journal"] and graded["lesson_id"] == lesson and graded["grade_type_id"] == grade_type

    # Переназначение: ещё одна попытка, прошлая сохраняется.
    await client.post(f"/assignments/{a['id']}/reassign", params={"student_id": str(olya)}, headers=bearer(teacher))
    second = (await client.post(f"/assignments/{a['id']}/start", headers=student(olya))).json()
    assert second["number"] == 2
    history = (await client.get(f"/assignments/{a['id']}", headers=student(olya))).json()["students"][0]["attempts"]
    assert [x["number"] for x in history] == [1, 2]


async def test_ordinary_submissions_cannot_target_assignments(client):
    teacher = uuid4()
    task = (await client.post("/tasks", json=CHOICE, headers=bearer(teacher))).json()
    resp = await client.post(f"/tasks/{task['id']}/submissions", headers=bearer(teacher),
                             json={"context_type": "assignment", "context_id": str(uuid4()), "answer": {"option_ids": []}})
    assert resp.json()["error"]["code"] == "use_attempt"


async def test_total_timer_auto_submits(client, fakes):
    teacher, pupil = uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    test = await make_test(client, teacher, tasks[:2], time_mode="total", time_limit_s=600)
    await link(teacher, pupil)
    a = await assign(client, teacher, test, target_type="student", target_id=str(pupil))
    attempt = (await client.post(f"/assignments/{a['id']}/start", headers=student(pupil))).json()
    assert attempt["ends_at"] is not None
    right = next(o["id"] for o in tasks[0]["options"] if o["is_correct"])
    await answer(client, attempt, tasks[0], pupil, option_ids=[right])

    async with db.sessionmaker() as s, s.begin():
        await s.execute(update(Attempt).where(Attempt.id == UUID(attempt["id"])).values(ends_at=datetime.now(UTC) - timedelta(minutes=1)))
    late = await answer(client, attempt, tasks[1], pupil, text="3.5")
    assert late.json()["error"]["code"] == "time_over"
    view = (await client.get(f"/attempts/{attempt['id']}", headers=student(pupil))).json()
    assert view["status"] == "submitted" and view["auto_submitted"] and view["score"] == 1 and view["grade"] == 3


async def test_per_task_timer_and_background_expiry(client, fakes):
    teacher, pupil = uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    test = await make_test(client, teacher, tasks[:2], time_mode="per_task", time_limit_s=60)
    await link(teacher, pupil)
    a = await assign(client, teacher, test, target_type="student", target_id=str(pupil))
    attempt = (await client.post(f"/assignments/{a['id']}/start", headers=student(pupil))).json()
    assert len(attempt["tasks"]) == 1 and attempt["current_ends_at"]  # следующие задания скрыты
    moved = (await client.post(f"/attempts/{attempt['id']}/next", headers=student(pupil))).json()
    assert moved["current_index"] == 1 and moved["tasks"][0]["locked"]
    back = await answer(client, attempt, tasks[0], pupil, option_ids=[tasks[0]["options"][0]["id"]])
    assert back.json()["error"]["code"] == "task_locked"
    await answer(client, attempt, tasks[1], pupil, text="3.5")

    # Ученик закрыл вкладку — время на задание вышло, фоновая задача сдаёт работу.
    async with db.sessionmaker() as s, s.begin():
        await s.execute(update(Attempt).where(Attempt.id == UUID(attempt["id"]))
                        .values(current_started_at=datetime.now(UTC) - timedelta(minutes=5)))
    await attempts.expire_job()
    view = (await client.get(f"/attempts/{attempt['id']}", headers=student(pupil))).json()
    assert view["status"] == "submitted" and view["auto_submitted"] and view["score"] == 1


async def test_deadline_and_personal_reassign(client, fakes):
    teacher, pupil = uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    test = await make_test(client, teacher, tasks[:1])
    await link(teacher, pupil)
    a = await assign(client, teacher, test, target_type="student", target_id=str(pupil),
                     deadline=(datetime.now(UTC) + timedelta(hours=1)).isoformat())
    async with db.sessionmaker() as s, s.begin():
        await s.execute(update(Assignment).where(Assignment.id == UUID(a["id"])).values(deadline=datetime.now(UTC) - timedelta(hours=1)))
    view = (await client.get(f"/assignments/{a['id']}", headers=student(pupil))).json()
    assert view["overdue"] and not view["can_start"]
    assert (await client.post(f"/assignments/{a['id']}/start", headers=student(pupil))).json()["error"]["code"] == "overdue"

    new_deadline = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    await client.post(f"/assignments/{a['id']}/reassign", params={"student_id": str(pupil), "deadline": new_deadline}, headers=bearer(teacher))
    view = (await client.get(f"/assignments/{a['id']}", headers=student(pupil))).json()
    assert view["can_start"] and not view["overdue"]
    assert (await outbox("assessment.assignment.reassigned"))[0]["data"]["student_id"] == str(pupil)


async def test_live_test_close(client, fakes):
    teacher, a1, a2 = uuid4(), uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    test = await make_test(client, teacher, tasks[:2], order_mode="random")
    gid = await group_of(fakes, teacher, a1, a2)
    lesson = str(uuid4())
    fakes.lessons[lesson] = str(teacher)
    a = await assign(client, teacher, test, kind="live", target_type="group", target_id=gid, lesson_id=lesson)
    attempt = (await client.post(f"/assignments/{a['id']}/start", headers=student(a1))).json()
    await answer(client, attempt, tasks[1], a1, text="3.5")
    closed = (await client.post(f"/assignments/{a['id']}/close", headers=bearer(teacher))).json()
    assert closed["closed"]
    row = next(s for s in closed["students"] if s["student_id"] == str(a1))
    assert row["attempts"][0]["status"] == "submitted" and row["attempts"][0]["score"] == 1
    assert (await client.post(f"/assignments/{a['id']}/start", headers=student(a2))).json()["error"]["code"] == "assignment_closed"
    # Чужой педагог не видит и не закрывает.
    assert (await client.post(f"/assignments/{a['id']}/close", headers=bearer(uuid4()))).status_code == 404


async def test_test_editing_rules(client, fakes):
    teacher, other = uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    foreign = (await client.post("/tasks", json=CHOICE, headers=bearer(other))).json()  # чужая приватная
    bad = await client.post("/tests", json={"title": "Т", "items": [{"task_id": foreign["id"]}]}, headers=bearer(teacher))
    assert bad.json()["error"]["code"] == "task_not_available"
    test = await make_test(client, teacher, tasks[:1])
    await link(teacher, uuid4())
    assert (await client.post(f"/tests/{test['id']}/assign", json={"target_type": "student", "target_id": str(uuid4())},
                              headers=bearer(teacher))).status_code == 404
    pupil = uuid4()
    await link(teacher, pupil)
    await assign(client, teacher, test, target_type="student", target_id=str(pupil))
    assert (await client.delete(f"/tests/{test['id']}", headers=bearer(teacher))).json()["error"]["code"] == "test_assigned"
    assert (await client.get(f"/tests/{test['id']}", headers=bearer(other))).status_code == 404
    listed = (await client.get("/tests", headers=bearer(teacher))).json()
    assert listed[0]["assignments_count"] == 1 and listed[0]["tasks_count"] == 1



async def test_opens_at_and_retakes_best_counts(client, fakes):
    """Тест откроется позже; несколько попыток — в журнал уходит лучшая."""
    teacher, pupil = uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    test = await make_test(client, teacher, tasks[:2])
    await link(teacher, pupil)
    lesson = str(uuid4())
    fakes.lessons[lesson] = str(teacher)
    a = await assign(client, teacher, test, kind="homework", target_type="student", target_id=str(pupil), lesson_id=lesson,
                     opens_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(), max_attempts=2,
                     grade_to_journal=True, grade_type_id=str(uuid4()))
    view = (await client.get(f"/assignments/{a['id']}", headers=student(pupil))).json()
    assert view["not_open_yet"] and not view["can_start"] and view["attempts_left"] == 2
    assert (await client.post(f"/assignments/{a['id']}/start", headers=student(pupil))).json()["error"]["code"] == "not_open_yet"
    async with db.sessionmaker() as s, s.begin():
        await s.execute(update(Assignment).where(Assignment.id == UUID(a["id"])).values(opens_at=datetime.now(UTC) - timedelta(minutes=1)))

    right = next(o["id"] for o in tasks[0]["options"] if o["is_correct"])
    first = (await client.post(f"/assignments/{a['id']}/start", headers=student(pupil))).json()
    await answer(client, first, tasks[0], pupil, option_ids=[right])
    await answer(client, first, tasks[1], pupil, text="3.5")
    await client.post(f"/attempts/{first['id']}/submit", headers=student(pupil))  # 100%
    view = (await client.get(f"/assignments/{a['id']}", headers=student(pupil))).json()
    assert view["can_start"] and view["attempts_left"] == 1

    second = (await client.post(f"/assignments/{a['id']}/start", headers=student(pupil))).json()
    assert second["number"] == 2
    await client.post(f"/attempts/{second['id']}/submit", headers=student(pupil))  # пусто — 0%
    graded = [e["data"] for e in await outbox("assessment.attempt.graded")]
    assert [g["percent"] for g in graded] == [100.0, 100.0]  # вторая попытка хуже — в итоге остаётся лучшая
    assert graded[-1]["attempt_id"] == first["id"] and graded[-1]["attempts"] == 2
    view = (await client.get(f"/assignments/{a['id']}", headers=student(pupil))).json()
    assert not view["can_start"] and view["attempts_left"] == 0
    assert (await client.post(f"/assignments/{a['id']}/start", headers=student(pupil))).json()["error"]["code"] == "already_submitted"


async def test_plain_test_unlimited_attempts(client, fakes):
    teacher, pupil = uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    test = await make_test(client, teacher, tasks[:1])
    await link(teacher, pupil)
    a = await assign(client, teacher, test, target_type="student", target_id=str(pupil), max_attempts=None,
                     lesson_id=str(uuid4()), title="  Тренировка   перед контрольной ")
    assert a["kind"] == "test" and a["lesson_id"] is None and a["max_attempts"] is None  # у просто теста урока нет
    # Своё название назначения; название теста сохраняется отдельно
    assert a["title"] == "Тренировка перед контрольной" and a["test_title"] == test["title"]
    same = await assign(client, teacher, test, target_type="student", target_id=str(pupil), title="   ")
    assert same["title"] == test["title"]
    for n in range(1, 4):
        t = (await client.post(f"/assignments/{a['id']}/start", headers=student(pupil))).json()
        assert t["number"] == n
        await client.post(f"/attempts/{t['id']}/submit", headers=student(pupil))
    view = (await client.get(f"/assignments/{a['id']}", headers=student(pupil))).json()
    assert view["can_start"] and view["attempts_left"] is None


async def test_proctoring(client, fakes):
    from .conftest import BASIC_TEACHERS, INTERNAL

    teacher, pupil, other = uuid4(), uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    test = await make_test(client, teacher, tasks[:1])
    await link(teacher, pupil)
    # Прокторинг — только на «Базовом».
    free = await client.post(f"/tests/{test['id']}/assign", json={"target_type": "student", "target_id": str(pupil), "proctoring": True},
                             headers=bearer(teacher))
    assert free.status_code == 403 and free.json()["error"]["code"] == "plan_required"
    BASIC_TEACHERS.add(str(teacher))
    a = await assign(client, teacher, test, target_type="student", target_id=str(pupil), proctoring=True)
    assert a["proctoring"] is True

    # Без согласия не начать; с согласием — попытка и событие «согласие».
    no = await client.post(f"/assignments/{a['id']}/start", headers=student(pupil))
    assert no.json()["error"]["code"] == "consent_required"
    t = (await client.post(f"/assignments/{a['id']}/start", json={"consent": True}, headers=student(pupil))).json()
    assert t["proctoring"] is True
    again = await client.post(f"/assignments/{a['id']}/start", headers=student(pupil))  # вернуться к идущей — без повторного согласия
    assert again.json()["id"] == t["id"]

    for kind in ("screen_share_started", "tab_hidden", "tab_visible", "focus_lost", "focus_back"):
        assert (await client.post(f"/attempts/{t['id']}/proctor-events", json={"kind": kind}, headers=student(pupil))).status_code == 204
    assert (await client.post(f"/attempts/{t['id']}/proctor-events", json={"kind": "consent"}, headers=student(pupil))).status_code == 422
    assert (await client.post(f"/attempts/{t['id']}/proctor-events", json={"kind": "tab_hidden"}, headers=student(other))).status_code == 404
    events = (await client.get(f"/attempts/{t['id']}/proctor-events", headers=bearer(teacher))).json()
    assert [e["kind"] for e in events] == ["consent", "screen_share_started", "tab_hidden", "tab_visible", "focus_lost", "focus_back"]
    view = (await client.get(f"/assignments/{a['id']}", headers=bearer(teacher))).json()
    assert view["students"][0]["proctor_alerts"] == 2  # вкладка и окно

    # Доступ к комнате прокторинга — для video.
    who = (await client.get(f"/internal/proctoring/{a['id']}", params={"user_id": str(pupil)}, headers=INTERNAL)).json()
    assert who["role"] == "student" and who["attempt_id"] == t["id"]
    boss = (await client.get(f"/internal/proctoring/{a['id']}", params={"user_id": str(teacher)}, headers=INTERNAL)).json()
    assert boss["role"] == "teacher" and boss["students"][0]["attempt_id"] == t["id"]
    stranger = await client.get(f"/internal/proctoring/{a['id']}", params={"user_id": str(other)}, headers=INTERNAL)
    assert stranger.status_code == 404


async def test_admin_removes_task_but_issued_tests_keep_working(client, fakes):
    teacher, pupil, boss = uuid4(), uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    test = await make_test(client, teacher, tasks[:2])
    await link(teacher, pupil)
    a = await assign(client, teacher, test, target_type="student", target_id=str(pupil))
    attempt = (await client.post(f"/assignments/{a['id']}/start", headers=student(pupil))).json()

    only_mod = await client.post(f"/admin/tasks/{tasks[0]['id']}/remove", json={"reason": "Ошибка в условии"},
                                 headers=bearer(boss, ("moderator",)))
    assert only_mod.status_code == 403
    removed = (await client.post(f"/admin/tasks/{tasks[0]['id']}/remove", json={"reason": "Ошибка в условии"},
                                 headers=bearer(boss, ("admin",)))).json()
    assert removed["status"] == "removed" and removed["review_comment"] == "Ошибка в условии"
    assert (await outbox("assessment.task.removed"))[0]["data"]["author_id"] == str(teacher)

    # Выданная работа продолжает работать, ученику сама задача вне теста не видна.
    view = (await client.get(f"/attempts/{attempt['id']}", headers=student(pupil))).json()
    assert len(view["tasks"]) == 2
    assert (await client.get(f"/tasks/{tasks[0]['id']}", headers=student(pupil))).status_code == 404
    # В новый тест не добавить, копию не сделать.
    bad = await client.post("/tests", json={"title": "Новый", "items": [{"task_id": tasks[0]["id"], "points": 1}]}, headers=bearer(teacher))
    assert bad.json()["error"]["code"] == "task_not_available"
    assert (await client.post(f"/tasks/{tasks[0]['id']}/copy", headers=bearer(teacher))).status_code == 404

    restored = (await client.post(f"/admin/tasks/{tasks[0]['id']}/restore", headers=bearer(boss, ("admin",)))).json()
    assert restored["status"] == "private"
