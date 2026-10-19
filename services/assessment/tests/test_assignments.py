from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import update

from app import attempts, handlers
from app.deps import db
from app.models import Assignment, Attempt, Task
from app.models import Test as Quiz

from .conftest import CHOICE, CODE, LONG, SHORT, apply, bearer, link, outbox, run_code_checks, student


async def make_tasks(client, teacher):
    out = []
    for body in (CHOICE, SHORT, CODE, LONG | {"file_mode": "optional"}):
        resp = await client.post("/tasks", json=body, headers=bearer(teacher))
        assert resp.status_code == 201, resp.text
        out.append(resp.json())
    return out


async def make_test(client, teacher, tasks, **settings):
    body = {"title": "Контрольная", "grade_level": 9, "items": [{"task_id": t["id"], "points": p} for t, p in zip(tasks, (1, 1, 2, 2), strict=False)]}
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

    # Оценка в журнал — только с типом оценки.
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
    bad = await client.post("/tests", json={"title": "Т", "grade_level": 7, "items": [{"task_id": foreign["id"]}]}, headers=bearer(teacher))
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
    assert listed[0]["assignments_count"] == 1 and listed[0]["tasks_count"] == 1 and listed[0]["grade_level"] == 9
    # Класс теста обязателен (1–11) и копируется в назначение — по нему фильтруют.
    no_grade = await client.post("/tests", json={"title": "Без класса", "items": []}, headers=bearer(teacher))
    assert no_grade.status_code == 422
    assert (await client.post("/tests", json={"title": "Т", "grade_level": 12, "items": []}, headers=bearer(teacher))).status_code == 422
    given = (await client.get("/assignments", params={"role": "teacher"}, headers=bearer(teacher))).json()
    assert given[0]["grade_level"] == 9



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

    # Ответы — только пока сервер видеосвязи видит показ экрана (событие от video, а не от страницы ученика).
    task = t["tasks"][0]["task"]
    answer = {"answer": {"option_ids": [task["options"][0]["id"]]}}
    blocked = await client.put(f"/attempts/{t['id']}/answers/{task['id']}", json=answer, headers=student(pupil))
    assert blocked.json()["error"]["code"] == "screen_required"
    assert (await client.get(f"/attempts/{t['id']}/status", headers=student(pupil))).json() == {
        "status": "in_progress", "screen_ok": False, "finished_by_teacher": False}
    now = datetime.now(UTC)

    async def screen(sharing: bool, at: datetime) -> None:
        await apply(handlers.on_video_event, "video.proctor.screen", assignment_id=a["id"], student_id=pupil, sharing=sharing,
                    at=at.isoformat())

    await screen(True, now)
    assert (await client.put(f"/attempts/{t['id']}/answers/{task['id']}", json=answer, headers=student(pupil))).status_code == 200
    await screen(False, now + timedelta(seconds=5))
    await screen(True, now + timedelta(seconds=2))  # запоздавшее событие не перетирает свежее
    blocked = await client.put(f"/attempts/{t['id']}/answers/{task['id']}", json=answer, headers=student(pupil))
    assert blocked.json()["error"]["code"] == "screen_required"
    view = (await client.get(f"/assignments/{a['id']}", headers=bearer(teacher))).json()
    assert view["students"][0]["attempts"][0]["screen_sharing"] is False
    assert [e["data"]["sharing"] for e in await outbox("assessment.attempt.screen")] == [True, False]  # только изменения

    # Педагог завершает работу досрочно: сохранённые ответы уходят на проверку, ученик больше не отвечает.
    assert (await client.post(f"/attempts/{t['id']}/finish", headers=student(pupil))).status_code == 403
    done = (await client.post(f"/attempts/{t['id']}/finish", headers=bearer(teacher))).json()
    assert done["status"] == "submitted" and done["finished_by_teacher"] and done["auto_submitted"] is False
    late = await client.put(f"/attempts/{t['id']}/answers/{task['id']}", json=answer, headers=student(pupil))
    assert late.json()["error"]["code"] == "finished_by_teacher"
    ev = (await outbox("assessment.attempt.submitted"))[-1]
    assert ev["data"]["by_teacher"] is True and ev["actor_id"] == str(teacher)
    kinds = [e["kind"] for e in (await client.get(f"/attempts/{t['id']}/proctor-events", headers=bearer(teacher))).json()]
    assert kinds[-1] == "finished_by_teacher"


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
    bad = await client.post("/tests", json={"title": "Новый", "grade_level": 7, "items": [{"task_id": tasks[0]["id"], "points": 1}]}, headers=bearer(teacher))
    assert bad.json()["error"]["code"] == "task_not_available"
    assert (await client.post(f"/tasks/{tasks[0]['id']}/copy", headers=bearer(teacher))).status_code == 404

    restored = (await client.post(f"/admin/tasks/{tasks[0]['id']}/restore", headers=bearer(boss, ("admin",)))).json()
    assert restored["status"] == "private"


async def test_solution_files_teacher_review_and_grade_scale(client, fakes):
    """Решение №34: файлы с решением к короткому ответу и выбору, итог — после проверки педагогом,
    свои критерии оценки, оценка в журнал без урока, ручная правка заданий и оценки."""
    teacher, pupil = uuid4(), uuid4()
    await link(teacher, pupil)
    tasks = await make_tasks(client, teacher)
    choice, short, long = tasks[0], tasks[1], tasks[3]
    # Файл с решением — только к короткому ответу и выбору.
    bad = await client.post("/tests", json={"title": "Т", "grade_level": 7, "items": [{"task_id": long["id"], "solution_file": True}]}, headers=bearer(teacher))
    assert bad.json()["error"]["code"] == "solution_file_not_allowed"
    test = (await client.post("/tests", json={"title": "Проверочная", "grade_level": 7, "items": [
        {"task_id": choice["id"], "points": 1}, {"task_id": short["id"], "points": 1, "solution_file": True}]}, headers=bearer(teacher))).json()
    assert [i["solution_file"] for i in test["items"]] == [False, True]

    # Критерии оценки — убывающие границы; в журнал — без урока, но с типом оценки.
    wrong_scale = await client.post(f"/tests/{test['id']}/assign", json={
        "target_type": "student", "target_id": str(pupil), "grade_scale": {"five": 60, "four": 70, "three": 50}}, headers=bearer(teacher))
    assert wrong_scale.status_code == 422
    grade_type = str(uuid4())
    a = await assign(client, teacher, test, target_type="student", target_id=str(pupil), grade_to_journal=True, grade_type_id=grade_type,
                     grade_scale={"five": 90, "four": 70, "three": 50})
    assert a["needs_review"] and a["grade_scale"] == {"5": 90, "4": 70, "3": 50} and a["lesson_id"] is None

    attempt = (await client.post(f"/assignments/{a['id']}/start", headers=student(pupil))).json()
    flags = {t["task"]["id"]: t["solution_file"] for t in attempt["tasks"]}
    assert flags == {choice["id"]: False, short["id"]: True}
    right = next(o["id"] for o in choice["options"] if o["is_correct"])
    # К выбору без галочки файл не прикрепить, к короткому ответу с галочкой — можно.
    no = await client.put(f"/attempts/{attempt['id']}/answers/{choice['id']}",
                          json={"answer": {"option_ids": [right]}, "file_ids": [fakes.file(pupil)]}, headers=student(pupil))
    assert no.json()["error"]["code"] == "files_not_allowed"
    await answer(client, attempt, choice, pupil, option_ids=[right])
    solution = fakes.file(pupil, "черновик.jpg")
    ok = await client.put(f"/attempts/{attempt['id']}/answers/{short['id']}",
                          json={"answer": {"text": "3.5"}, "file_ids": [solution]}, headers=student(pupil))
    assert ok.status_code == 200, ok.text
    done = (await client.post(f"/attempts/{attempt['id']}/submit", headers=student(pupil))).json()

    # Всё проверилось автоматически: ученик видит, что верно, но итога и оценки нет до проверки педагогом.
    assert not done["checked"] and done["score"] is None and done["grade"] is None and done["needs_review"]
    statuses = {t["task"]["id"]: (t["result"]["status"], [f["filename"] for f in t["result"]["files"]]) for t in done["tasks"]}
    assert statuses == {choice["id"]: ("correct", []), short["id"]: ("correct", ["черновик.jpg"])}
    assert await outbox("assessment.attempt.graded") == []
    given = (await client.get(f"/assignments/{a['id']}", headers=bearer(teacher))).json()
    assert given["students"][0]["attempts"][0]["checked"] is False  # «ждёт проверки» у педагога

    # Проверять может только педагог.
    assert (await client.post(f"/attempts/{attempt['id']}/review", json={}, headers=student(pupil))).status_code in (403, 404)

    # Педагог не засчитал выбор (решение в файле не сходится): 1 из 2 = 50% → по критериям «3».
    reviewed = (await client.post(f"/attempts/{attempt['id']}/review", json={"tasks": {choice["id"]: False}},
                                  headers=bearer(teacher))).json()
    assert reviewed["checked"] and reviewed["score"] == 1 and reviewed["percent"] == 50 and reviewed["grade"] == 3
    graded = (await outbox("assessment.attempt.graded"))[-1]["data"]
    assert graded["grade"] == 3 and graded["to_journal"] and graded["group_id"] is None and graded["assigned_at"]
    assert not graded["by_teacher"]
    seen = (await client.get(f"/attempts/{attempt['id']}", headers=student(pupil))).json()
    assert seen["grade"] == 3 and {t["task"]["id"]: t["result"]["status"] for t in seen["tasks"]}[choice["id"]] == "incorrect"

    # Оценку можно поставить вручную; null — снова по критериям.
    manual = (await client.post(f"/attempts/{attempt['id']}/review", json={"grade": 5}, headers=bearer(teacher))).json()
    assert manual["grade"] == 5 and manual["grade_override"] == 5
    assert (await outbox("assessment.attempt.graded"))[-1]["data"]["by_teacher"]
    auto = (await client.post(f"/attempts/{attempt['id']}/review", json={"grade": None}, headers=bearer(teacher))).json()
    assert auto["grade"] == 3 and auto["grade_override"] is None


async def test_teacher_overrides_auto_checked_tasks(client, fakes):
    """Даже без файлов с решением педагог может засчитать неверное или пустое задание — итог пересчитывается."""
    teacher, pupil = uuid4(), uuid4()
    await link(teacher, pupil)
    tasks = await make_tasks(client, teacher)
    choice, short = tasks[0], tasks[1]
    test = (await client.post("/tests", json={"title": "Т", "grade_level": 7, "items": [
        {"task_id": choice["id"], "points": 1}, {"task_id": short["id"], "points": 1}]}, headers=bearer(teacher))).json()
    a = await assign(client, teacher, test, target_type="student", target_id=str(pupil))
    assert not a["needs_review"]
    attempt = (await client.post(f"/assignments/{a['id']}/start", headers=student(pupil))).json()
    await answer(client, attempt, short, pupil, text="3,4")  # неверно; на выбор не ответил
    done = (await client.post(f"/attempts/{attempt['id']}/submit", headers=student(pupil))).json()
    assert done["checked"] and done["score"] == 0 and done["grade"] == 2

    fixed = (await client.post(f"/attempts/{attempt['id']}/review", json={"tasks": {short["id"]: True, choice["id"]: True}},
                               headers=bearer(teacher))).json()
    assert fixed["score"] == 2 and fixed["grade"] == 5
    results = {t["task"]["id"]: t["result"]["status"] for t in fixed["tasks"]}
    assert results == {choice["id"]: "correct", short["id"]: "correct"}
    unknown = await client.post(f"/attempts/{attempt['id']}/review", json={"tasks": {str(uuid4()): True}}, headers=bearer(teacher))
    assert unknown.status_code == 422


async def test_remove_assignment_and_students(client, fakes):
    """Убрать работу у одного ученика, у всех несдавших, удалить целиком — вместе с попытками."""
    teacher, olya, petya, vasya = uuid4(), uuid4(), uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    test = await make_test(client, teacher, tasks[:2])
    gid = await group_of(fakes, teacher, olya, petya, vasya)
    a = await assign(client, teacher, test, target_type="group", target_id=gid, max_attempts=None)
    done = (await client.post(f"/assignments/{a['id']}/start", headers=student(olya))).json()
    await client.post(f"/attempts/{done['id']}/submit", headers=student(olya))
    started = (await client.post(f"/assignments/{a['id']}/start", headers=student(petya))).json()
    assert started["status"] == "in_progress"

    # Только педагог-автор.
    assert (await client.post(f"/assignments/{a['id']}/remove-students", json={"not_submitted": True},
                              headers=student(olya))).status_code in (403, 404)
    assert (await client.delete(f"/assignments/{a['id']}", headers=bearer(uuid4()))).status_code == 404

    # У несдавших (Петя решает, Вася не начал) — убрать; у Оли остаётся.
    res = (await client.post(f"/assignments/{a['id']}/remove-students", json={"not_submitted": True}, headers=bearer(teacher))).json()
    assert res == {"removed": 2, "deleted": False}
    left = (await client.get(f"/assignments/{a['id']}", headers=bearer(teacher))).json()
    assert [s["student_id"] for s in left["students"]] == [str(olya)]
    assert (await client.get(f"/attempts/{started['id']}", headers=student(petya))).status_code == 404
    removed = (await outbox("assessment.assignment.students_removed"))[-1]["data"]
    assert sorted(removed["student_ids"]) == sorted([str(petya), str(vasya)])
    assert (await client.get(f"/assignments/{a['id']}", headers=student(vasya))).status_code == 404

    # Убрали последнего — назначение удалено целиком.
    last = (await client.post(f"/assignments/{a['id']}/remove-students", json={"student_ids": [str(olya)]}, headers=bearer(teacher))).json()
    assert last == {"removed": 1, "deleted": True}
    assert (await client.get(f"/assignments/{a['id']}", headers=bearer(teacher))).status_code == 404
    assert (await outbox("assessment.assignment.deleted"))[-1]["data"]["student_ids"] == [str(olya)]

    # Удалить целиком сразу.
    b = await assign(client, teacher, test, target_type="group", target_id=gid)
    t = (await client.post(f"/assignments/{b['id']}/start", headers=student(olya))).json()
    await client.post(f"/attempts/{t['id']}/submit", headers=student(olya))
    assert (await client.delete(f"/assignments/{b['id']}", headers=bearer(teacher))).status_code == 204
    assert (await client.get(f"/assignments/{b['id']}", headers=bearer(teacher))).status_code == 404
    assert (await client.get(f"/attempts/{t['id']}", headers=student(olya))).status_code == 404


async def test_test_linked_to_course_module(client, fakes):
    """Привязка теста к модулю (решения №43, 44): проверка в content, оформление — как у курса, работы видны по модулю."""
    teacher, other, olya = uuid4(), uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    mine, foreign, public = fakes.module(teacher), fakes.module(other), fakes.module(other, theme="classic", status="published")
    body = {"title": "К теме", "grade_level": 7, "items": [{"task_id": tasks[0]["id"]}]}

    for bad in (str(uuid4()), foreign):  # нет такого модуля или чужой черновик
        resp = await client.post("/tests", json=body | {"module_id": bad}, headers=bearer(teacher))
        assert resp.status_code == 422 and resp.json()["error"]["code"] == "module_not_available"
    plain = (await client.post("/tests", json=body, headers=bearer(teacher))).json()
    assert plain["theme"] == "classic" and plain["module"] is None
    assert (await client.post("/tests", json=body | {"module_id": public}, headers=bearer(teacher))).status_code == 201

    test = (await client.post("/tests", json=body | {"module_id": mine, "theme": "classic"}, headers=bearer(teacher))).json()
    assert test["theme"] == "course"  # выбрать оформление нельзя: привязан — как у курса
    assert test["module"]["title"] == "Уравнения" and test["module"]["course_title"] == "Математика 7"
    listed = (await client.get("/tests", params={"module_id": mine}, headers=bearer(teacher))).json()
    assert [t["id"] for t in listed] == [test["id"]] and listed[0]["module"]["id"] == mine

    await link(teacher, olya)
    a = await assign(client, teacher, test, target_type="student", target_id=str(olya))
    assert a["settings"]["theme"] == "comics" and a["module"]["id"] == mine
    assert (await assign(client, teacher, plain, target_type="student", target_id=str(olya)))["settings"]["theme"] == "classic"
    by_module = (await client.get("/assignments", params={"module_id": mine}, headers=student(olya))).json()
    assert [x["id"] for x in by_module] == [a["id"]]

    # Курс сменил тему — новые работы её подхватят; отвязали — модуль пропал, у выданной работы остался.
    fakes.modules[mine]["course_theme"] = "classic"
    assert (await assign(client, teacher, test, target_type="student", target_id=str(olya)))["settings"]["theme"] == "classic"
    unlinked = (await client.put(f"/tests/{test['id']}", json=body, headers=bearer(teacher))).json()
    assert unlinked["module"] is None and unlinked["theme"] == "classic"
    assert (await client.get(f"/assignments/{a['id']}", headers=student(olya))).json()["module"]["id"] == mine


async def test_course_tests_visibility_and_self_study(client, fakes):
    """Тесты к модулю (решение №46): у автора курса — публичный (ученикам и педагогам) и «для педагогов» (всем педагогам),
    видны после того, как модератор примет их с курсом; у любого другого педагога — личный (только ему).
    Публичный тест ученики проходят сами; педагоги ученика видят такие работы; тесты автора назначает любой педагог."""
    author, teacher, olya, stranger = uuid4(), uuid4(), uuid4(), uuid4()
    tasks = await make_tasks(client, author)
    mod = fakes.module(author)
    course = fakes.modules[mod]["course_id"]
    body = {"title": "Практическая работа", "grade_level": 7, "items": [{"task_id": tasks[0]["id"]}], "module_id": mod}

    assert (await client.post("/tests", json=body | {"module_id": None, "shared": True}, headers=bearer(author))).status_code == 422
    other_mod = fakes.module(stranger, status="published")
    resp = await client.post("/tests", json=body | {"module_id": other_mod, "shared": True}, headers=bearer(author))
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "shared_not_author"
    shared = (await client.post("/tests", json=body | {"shared": True}, headers=bearer(author))).json()
    for_teachers = (await client.post("/tests", json=body | {"title": "Контрольная"}, headers=bearer(author))).json()
    assert (shared["visibility"], for_teachers["visibility"], shared["published"]) == ("public", "teachers", False)
    # Пока курс не принят модератором, тесты автора не видны никому, кроме него.
    await link(author, olya)
    assert (await client.get("/course-tests", params={"module_id": mod}, headers=student(olya))).json() == []
    assert (await client.post(f"/course-tests/{shared['id']}/start", headers=student(olya))).status_code == 404

    # Курс на проверке: задачи тестов автора уходят на проверку вместе с ним, тесты не меняются.
    await apply(handlers.on_content_event, "content.course.submitted", course_id=course, author_id=author, task_ids=[])
    assert (await client.get(f"/tasks/{tasks[0]['id']}", headers=bearer(author))).json()["status"] == "pending"
    fakes.modules[mod]["course_status"] = "pending"
    resp = await client.put(f"/tests/{shared['id']}", json=body | {"shared": True, "title": "Новое"}, headers=bearer(author))
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "course_in_review"

    # Принят: задачи публичные, тесты автора видны — публичный ученикам и педагогам, «для педагогов» — педагогам.
    fakes.modules[mod]["course_status"] = "published"
    await apply(handlers.on_content_event, "content.course.published", course_id=course, author_id=author, task_ids=[])
    assert (await client.get(f"/tasks/{tasks[0]['id']}", headers=bearer(author))).json()["status"] == "published"
    seen = (await client.get("/course-tests", params={"module_id": mod}, headers=student(olya))).json()
    assert [(t["title"], t["visibility"]) for t in seen] == [("Практическая работа", "public")] and seen[0]["self_assignment"] is None
    by_teacher = (await client.get("/course-tests", params={"module_id": mod}, headers=bearer(teacher))).json()
    assert [(t["title"], t["visibility"]) for t in by_teacher] == [("Практическая работа", "public"), ("Контрольная", "teachers")]
    assert (await client.post(f"/course-tests/{for_teachers['id']}/start", headers=student(olya))).status_code == 404
    # Свой тест к модулю чужого опубликованного курса — личный: виден только автору теста.
    teacher_tasks = await make_tasks(client, teacher)
    own = (await client.post("/tests", json=body | {"title": "Моя проверочная", "items": [{"task_id": teacher_tasks[0]["id"]}]},
                             headers=bearer(teacher))).json()
    assert own["visibility"] == "private"
    assert (await client.get(f"/course-tests/{own['id']}", headers=bearer(stranger))).status_code == 404  # личный — только автору

    # Самостоятельно: без срока и журнала, попыток сколько угодно; в обычных списках не показывается.
    attempt = (await client.post(f"/course-tests/{shared['id']}/start", headers=student(olya))).json()
    assert attempt["self_study"] and attempt["settings"]["theme"] == "comics"
    choice = tasks[0]
    right = next(o["id"] for o in (await client.get(f"/tasks/{choice['id']}", headers=bearer(author))).json()["options"] if o["is_correct"])
    await answer(client, attempt, choice, olya, option_ids=[right])
    done = (await client.post(f"/attempts/{attempt['id']}/submit", headers=student(olya))).json()
    assert done["status"] == "submitted" and done["grade"] == 5
    again = (await client.post(f"/course-tests/{shared['id']}/start", headers=student(olya))).json()
    assert again["number"] == 2 and again["assignment_id"] == attempt["assignment_id"]
    assert (await client.get("/assignments", headers=student(olya))).json() == []

    # Педагог ученика видит его самостоятельную работу и попытку, но не проверяет и не удаляет её.
    await link(teacher, olya)
    work = (await client.get(f"/students/{olya}/self-work", headers=bearer(teacher))).json()
    assert [w["title"] for w in work] == ["Практическая работа"]
    assert (await client.get(f"/attempts/{attempt['id']}", headers=bearer(teacher))).status_code == 200
    assert (await client.post(f"/attempts/{attempt['id']}/review", json={"marks": {}}, headers=bearer(teacher))).status_code == 404

    # Любой педагог назначает тесты автора — и публичный, и «для педагогов»; чужой личный — нет.
    brief = (await client.get(f"/course-tests/{for_teachers['id']}", headers=bearer(teacher))).json()
    assert (brief["title"], brief["visibility"], brief["tasks_count"]) == ("Контрольная", "teachers", 1)
    a = await assign(client, teacher, for_teachers, target_type="student", target_id=str(olya))
    assert a["teacher_id"] == str(teacher) and a["settings"]["theme"] == "comics"
    await link(stranger, olya)
    assert (await client.post(f"/tests/{own['id']}/assign", json={"target_type": "student", "target_id": str(olya)},
                              headers=bearer(stranger))).status_code == 404

    # Правка принятого теста опубликованного курса — предложение: все видят прежнюю версию, пока модератор
    # не примет черновик изменений курса.
    edited = (await client.put(f"/tests/{shared['id']}", json=body | {"shared": True, "title": "Практическая работа №1"},
                               headers=bearer(author))).json()
    assert (edited["title"], edited["pending"]) == ("Практическая работа №1", True)
    assert [t["title"] for t in (await client.get("/course-tests", params={"module_id": mod}, headers=student(olya))).json()] \
        == ["Практическая работа"]
    assert (await client.delete(f"/tests/{shared['id']}", headers=bearer(author))).status_code == 409
    draft = str(uuid4())
    await apply(handlers.on_content_event, "content.course.published", course_id=course, author_id=author, task_ids=[],
                revision_id=draft, revision_of=course)
    assert [t["title"] for t in (await client.get("/course-tests", params={"module_id": mod}, headers=student(olya))).json()] \
        == ["Практическая работа №1"]
    assert (await client.get(f"/tests/{shared['id']}", headers=bearer(author))).json()["pending"] is False
    assert (await client.put(f"/tests/{own['id']}", json=body | {"title": "Моя 2", "items": [{"task_id": teacher_tasks[0]["id"]}]},
                             headers=bearer(teacher))).status_code == 200  # личный тест — правится сразу


async def test_course_test_read_only_for_teachers(client, fakes):
    """Тест автора курса, видный педагогу, открывается ему только для просмотра — с задачами, условиями и ответами,
    даже если задачи у автора ещё личные (решение №46). Ученику и чужому личному тесту — 404."""
    author, teacher, olya = uuid4(), uuid4(), uuid4()
    tasks = await make_tasks(client, author)
    mod = fakes.module(author, status="published")
    body = {"title": "Контрольная", "grade_level": 7, "items": [{"task_id": tasks[0]["id"], "points": 2}], "module_id": mod}
    test = (await client.post("/tests", json=body, headers=bearer(author))).json()
    task_url = f"/tasks/{tasks[0]['id']}"
    # Пока тест не принят — не виден ни сам, ни его личные задачи.
    assert (await client.get(f"/tests/{test['id']}", headers=bearer(teacher))).status_code == 404
    assert (await client.get(task_url, headers=bearer(teacher))).status_code == 404
    # Принят (задачи остались личными — так было у тестов, принятых до решения №46).
    async with db.sessionmaker() as s, s.begin():
        await s.execute(update(Quiz).where(Quiz.id == test["id"]).values(published_at=datetime.now(UTC)))
        await s.execute(update(Task).where(Task.id == tasks[0]["id"]).values(status="private"))

    seen = (await client.get(f"/tests/{test['id']}", headers=bearer(teacher))).json()
    assert (seen["title"], seen["can_edit"], seen["max_score"], seen["visibility"]) == ("Контрольная", False, 2, "teachers")
    assert [i["task_id"] for i in seen["items"]] == [tasks[0]["id"]]
    task = (await client.get(task_url, headers=bearer(teacher))).json()
    assert task["explanation"] and any(o["is_correct"] for o in task["options"])
    assert (await client.get(f"/tests/{test['id']}", headers=bearer(author))).json()["can_edit"] is True
    # Править чужой тест нельзя; ученику и непедагогу — не виден.
    assert (await client.put(f"/tests/{test['id']}", json=body, headers=bearer(teacher))).status_code == 404
    assert (await client.get(f"/tests/{test['id']}", headers=student(olya))).status_code == 403
    assert (await client.get(task_url, headers=student(olya))).status_code == 404
    # Личный тест педагога к чужому курсу другим не виден.
    mine = await make_tasks(client, teacher)
    own = (await client.post("/tests", json=body | {"title": "Моя", "items": [{"task_id": mine[0]["id"]}]}, headers=bearer(teacher))).json()
    assert (await client.get(f"/tests/{own['id']}", headers=bearer(uuid4()))).status_code == 404


async def test_staff_course_tests_publish_at_once(client, fakes):
    """Курсы штатных редакторов публикуются без очереди — их тесты к опубликованному курсу видны сразу,
    задачи в них сразу публичные (решение №46)."""
    admin, teacher = uuid4(), uuid4()
    tasks = await make_tasks(client, admin)
    mod = fakes.module(admin, status="published")
    t = (await client.post("/tests", json={"title": "Проверка", "grade_level": 7, "items": [{"task_id": tasks[1]["id"]}],
                                           "module_id": mod}, headers=bearer(admin, ("admin",)))).json()
    assert (t["visibility"], t["published"], t["pending"]) == ("teachers", True, False)
    assert (await client.get(f"/tasks/{tasks[1]['id']}", headers=bearer(admin))).json()["status"] == "published"
    assert [x["title"] for x in (await client.get("/course-tests", params={"module_id": mod}, headers=bearer(teacher))).json()] \
        == ["Проверка"]


async def test_variants_in_one_assignment(client, fakes):
    """Варианты (решение №48): одна работа, у учеников разные тесты — вручную или поровну автоматически.
    Ученик проходит свой вариант, баллы — по нему; вариант меняется, пока ученик не начал."""
    teacher = uuid4()
    pupils = [uuid4() for _ in range(5)]
    tasks = await make_tasks(client, teacher)
    first = await make_test(client, teacher, tasks[:1], title="Вариант 1")  # выбор ответа, 1 балл
    second = await make_test(client, teacher, tasks[1:3], title="Вариант 2")  # короткий и код, по 1 баллу
    gid = await group_of(fakes, teacher, *pupils)

    resp = await client.post(f"/tests/{first['id']}/assign", headers=bearer(teacher),
                             json={"target_type": "group", "target_id": gid, "variant_test_ids": [first["id"]]})
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "variant_duplicate"
    a = await assign(client, teacher, first, target_type="group", target_id=gid, variant_test_ids=[second["id"]],
                     variants={str(pupils[0]): 2})
    assert [(v["number"], v["test_title"], v["tasks_count"], v["max_score"]) for v in a["variants"]] \
        == [(1, "Вариант 1", 1, 1), (2, "Вариант 2", 2, 2)]
    by = {s["student_id"]: s["variant"] for s in a["students"]}
    assert by[str(pupils[0])] == 2 and sorted(by.values()).count(1) in (2, 3) and sorted(by.values()).count(2) in (2, 3)

    # Ученик видит и проходит только свой вариант.
    two = pupils[0]
    mine = (await client.get(f"/assignments/{a['id']}", headers=student(two))).json()
    assert (mine["tasks_count"], mine["max_score"], mine["variants"]) == (2, 2, None)
    attempt = (await client.post(f"/assignments/{a['id']}/start", headers=student(two))).json()
    assert sorted(t["task"]["id"] for t in attempt["tasks"]) == sorted(t["id"] for t in tasks[1:3])
    await answer(client, attempt, tasks[1], two, text="3.5")
    done = (await client.post(f"/attempts/{attempt['id']}/submit", headers=student(two))).json()
    assert done["max_score"] == 2

    one = next(p for p in pupils if by[str(p)] == 1)
    first_attempt = (await client.post(f"/assignments/{a['id']}/start", headers=student(one))).json()
    assert [t["task"]["id"] for t in first_attempt["tasks"]] == [tasks[0]["id"]]

    # Вариант меняется, пока ученик не начал; начал — уже нет.
    idle = next(p for p in pupils if p not in (two, one))
    url = f"/assignments/{a['id']}/students/{idle}/variant"
    changed = (await client.put(url, json={"variant": 2}, headers=bearer(teacher))).json()
    assert next(s["variant"] for s in changed["students"] if s["student_id"] == str(idle)) == 2
    assert (await client.put(url, json={"variant": 3}, headers=bearer(teacher))).status_code == 422
    locked = await client.put(f"/assignments/{a['id']}/students/{one}/variant", json={"variant": 2}, headers=bearer(teacher))
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "variant_locked"
    assert (await client.put(url, json={"variant": 1}, headers=student(idle))).status_code == 403

    # Свои настройки у каждого варианта; назначение засчитано обоим тестам — удалить тест варианта нельзя.
    timed = await make_test(client, teacher, tasks[1:2], title="Вариант 3", time_mode="total", time_limit_s=600)
    b = await assign(client, teacher, first, target_type="group", target_id=gid, variant_test_ids=[timed["id"]],
                     variants={str(p): 2 for p in pupils})
    assert [v["settings"]["time_mode"] for v in b["variants"]] == ["none", "total"]
    started = (await client.post(f"/assignments/{b['id']}/start", headers=student(pupils[1]))).json()
    assert started["settings"]["time_limit_s"] == 600 and started["ends_at"]
    tests = {t["id"]: t["assignments_count"] for t in (await client.get("/tests", headers=bearer(teacher))).json()}
    assert (tests[first["id"]], tests[second["id"]], tests[timed["id"]]) == (2, 1, 1)
    deleted = await client.delete(f"/tests/{second['id']}", headers=bearer(teacher))
    assert deleted.status_code == 409 and deleted.json()["error"]["code"] == "test_assigned"

    # Без вариантов — как раньше.
    plain = await assign(client, teacher, first, target_type="group", target_id=gid)
    assert plain["variants"] is None and {s["variant"] for s in plain["students"]} == {None}


async def test_code_check_modes(client, fakes):
    """Три способа проверки кода в тесте (решение №49): после сдачи, по кнопке «Проверить» (сколько угодно раз,
    ученик видит, сколько тестов не прошло; в оценку — лучшая проверка) и педагогом (без тестов)."""
    teacher, olya = uuid4(), uuid4()
    tasks = []
    for title in ("Код после сдачи", "Код по кнопке", "Код педагогу"):
        resp = await client.post("/tasks", json=CODE | {"title": title}, headers=bearer(teacher))
        tasks.append(resp.json())
    after, live, manual = tasks
    body = {"title": "Программирование", "grade_level": 9, "items": [
        {"task_id": after["id"]}, {"task_id": live["id"], "code_check": "live"}, {"task_id": manual["id"], "code_check": "manual"},
    ]}
    test = (await client.post("/tests", json=body, headers=bearer(teacher))).json()
    assert [i["code_check"] for i in test["items"]] == ["after", "live", "manual"]
    await link(teacher, olya)
    a = await assign(client, teacher, test, target_type="student", target_id=str(olya))
    assert a["needs_review"]  # код проверяет педагог — итог после проверки
    attempt = (await client.post(f"/assignments/{a['id']}/start", headers=student(olya))).json()
    by = {t["task"]["id"]: t for t in attempt["tasks"]}
    assert (by[after["id"]]["code_check"], by[live["id"]]["code_check"], by[manual["id"]]["code_check"]) == ("after", "live", "manual")

    url = f"/attempts/{attempt['id']}/tasks/{{}}/check"
    no = await client.post(url.format(after["id"]), json={"code": "print(1)"}, headers=student(olya))
    assert no.status_code == 409 and no.json()["error"]["code"] == "check_not_allowed"
    # Проверка по кнопке: неверно — видно, сколько тестов не прошло; пока идёт — вторую не запустить.
    first = (await client.post(url.format(live["id"]), json={"code": "print(41)"}, headers=student(olya))).json()
    assert next(t for t in first["tasks"] if t["task"]["id"] == live["id"])["check"]["status"] == "checking"
    busy = await client.post(url.format(live["id"]), json={"code": "print(41)"}, headers=student(olya))
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "check_running"
    await run_code_checks()
    seen = (await client.get(f"/attempts/{attempt['id']}", headers=student(olya))).json()
    check = next(t for t in seen["tasks"] if t["task"]["id"] == live["id"])["check"]
    assert (check["status"], check["failed"], check["total"], check["count"], check["passed_once"]) == ("incorrect", 1, 2, 1, False)
    # Верно — засчитается, даже если потом код испортить: в оценку — лучшая проверка.
    await client.post(url.format(live["id"]), json={"code": "print('correct')"}, headers=student(olya))
    await run_code_checks()
    await client.post(url.format(live["id"]), json={"code": "print(0)"}, headers=student(olya))
    await run_code_checks()
    seen = (await client.get(f"/attempts/{attempt['id']}", headers=student(olya))).json()
    check = next(t for t in seen["tasks"] if t["task"]["id"] == live["id"])["check"]
    assert (check["status"], check["count"], check["passed_once"]) == ("incorrect", 3, True)
    assert "run_log" not in str(check)

    await answer(client, attempt, after, olya, code="print('correct')")
    await answer(client, attempt, manual, olya, code="print(5)")
    runs = len(fakes.runs)
    done = (await client.post(f"/attempts/{attempt['id']}/submit", headers=student(olya))).json()
    await run_code_checks()
    assert len(fakes.runs) == runs + 1  # прогон — только у кода «после сдачи»; по кнопке — без нового прогона, педагогу — без тестов
    result = (await client.get(f"/attempts/{attempt['id']}", headers=bearer(teacher))).json()
    status = {t["task"]["id"]: t["result"]["status"] for t in result["tasks"]}
    assert (status[after["id"]], status[live["id"]], status[manual["id"]]) == ("correct", "correct", "pending_review")
    assert not result["checked"] and done["needs_review"]
    # Педагог проверил код — итог виден.
    reviewed = (await client.post(f"/attempts/{attempt['id']}/review", json={"tasks": {manual["id"]: True}},
                                  headers=bearer(teacher))).json()
    assert reviewed["checked"] and reviewed["score"] == 3


async def test_result_after_review(client, fakes):
    """«Оценка после проверки педагогом» (решение №49): даже автоматически проверенную работу ученик видит с итогом
    только после проверки."""
    teacher, olya = uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    test = await make_test(client, teacher, tasks[:1])
    await link(teacher, olya)
    a = await assign(client, teacher, test, target_type="student", target_id=str(olya), result_after_review=True)
    assert a["result_after_review"] and a["needs_review"]
    attempt = (await client.post(f"/assignments/{a['id']}/start", headers=student(olya))).json()
    right = next(o["id"] for o in (await client.get(f"/tasks/{tasks[0]['id']}", headers=bearer(teacher))).json()["options"] if o["is_correct"])
    await answer(client, attempt, tasks[0], olya, option_ids=[right])
    done = (await client.post(f"/attempts/{attempt['id']}/submit", headers=student(olya))).json()
    assert not done["checked"] and done["grade"] is None and done["score"] is None
    # До проверки ученик не видит и «верно/неверно», и разбор; педагог — видит.
    assert done["results_hidden"] and done["tasks"][0]["result"] is None and not done["tasks"][0]["task"]["explanation"]
    teacher_view = (await client.get(f"/attempts/{attempt['id']}", headers=bearer(teacher))).json()
    assert not teacher_view["results_hidden"] and teacher_view["tasks"][0]["result"]["status"] == "correct"
    reviewed = (await client.post(f"/attempts/{attempt['id']}/review", json={"tasks": {}}, headers=bearer(teacher))).json()
    assert reviewed["checked"] and reviewed["grade"] == 5
    mine = (await client.get(f"/attempts/{attempt['id']}", headers=student(olya))).json()
    assert mine["score"] == 1 and mine["grade"] == 5 and not mine["results_hidden"] and mine["tasks"][0]["result"]["status"] == "correct"


async def test_review_partial_points(client, fakes):
    """Педагог при проверке ставит любые баллы за задание — от 0 до максимума (например, 1 из 2 за почти верный код)."""
    teacher, olya = uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    test = await make_test(client, teacher, tasks[:3])  # выбор 1 балл, короткий 1, код 2
    await link(teacher, olya)
    a = await assign(client, teacher, test, target_type="student", target_id=str(olya))
    attempt = (await client.post(f"/assignments/{a['id']}/start", headers=student(olya))).json()
    await answer(client, attempt, tasks[2], olya, code="print(41)")
    await client.post(f"/attempts/{attempt['id']}/submit", headers=student(olya))
    await run_code_checks()
    url = f"/attempts/{attempt['id']}/review"
    bad = await client.post(url, json={"points": {tasks[2]["id"]: 3}}, headers=bearer(teacher))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "points_out_of_range"
    done = (await client.post(url, json={"points": {tasks[2]["id"]: 1.5, tasks[0]["id"]: 1}}, headers=bearer(teacher))).json()
    code = next(t for t in done["tasks"] if t["task"]["id"] == tasks[2]["id"])
    assert (code["earned"], code["result"]["status"], done["score"], done["max_score"]) == (1.5, "reviewed", 2.5, 4)
    # Оценка за код вручную — с комментарием, как у развёрнутого ответа.
    sub_id = code["result"]["id"]
    reviewed = await client.post(f"/submissions/{sub_id}/review", json={"score": 0.5, "comment": "Не учтены отрицательные"},
                                 headers=bearer(teacher))
    assert reviewed.status_code == 200 and reviewed.json()["teacher_comment"] == "Не учтены отрицательные"
    after = (await client.get(f"/attempts/{attempt['id']}", headers=bearer(teacher))).json()
    assert next(t for t in after["tasks"] if t["task"]["id"] == tasks[2]["id"])["earned"] == 1


async def test_staff_task_added_to_published_course(client, fakes):
    """Задача, которую штатный редактор добавил в опубликованный курс, публикуется сразу; чужая — нет (решение №51)."""
    editor, other = uuid4(), uuid4()
    mine = (await make_tasks(client, editor))[0]
    foreign = (await make_tasks(client, other))[0]
    await apply(handlers.on_content_event, "content.course.tasks_added", course_id=uuid4(), author_id=editor,
                task_ids=[mine["id"], foreign["id"]])
    assert (await client.get(f"/tasks/{mine['id']}", headers=bearer(editor))).json()["status"] == "published"
    assert (await client.get(f"/tasks/{foreign['id']}", headers=bearer(other))).json()["status"] == "private"


async def test_update_assigned_work(client, fakes):
    """Выданную работу можно поправить (решение №52): сроки, попытки, критерии, баллы — сданные попытки пересчитываются,
    оценка в журнале обновляется; состав не меняется."""
    teacher, olya = uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    test = await make_test(client, teacher, tasks[:2])  # выбор и короткий — по 1 баллу
    await link(teacher, olya)
    a = await assign(client, teacher, test, target_type="student", target_id=str(olya), grade_to_journal=True,
                     grade_type_id=str(uuid4()))
    attempt = (await client.post(f"/assignments/{a['id']}/start", headers=student(olya))).json()
    right = next(o["id"] for o in (await client.get(f"/tasks/{tasks[0]['id']}", headers=bearer(teacher))).json()["options"] if o["is_correct"])
    await answer(client, attempt, tasks[0], olya, option_ids=[right])  # верно 1 из 2 — 50%, оценка 3
    done = (await client.post(f"/attempts/{attempt['id']}/submit", headers=student(olya))).json()
    assert (done["score"], done["max_score"], done["grade"]) == (1, 2, 3)

    url = f"/assignments/{a['id']}"
    bad = await client.patch(url, json={"points": [[1]]}, headers=bearer(teacher))
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "points_shape"
    assert (await client.patch(url, json={"title": "x"}, headers=student(olya))).status_code == 403
    # Баллы 3 и 1: верное задание — 3 из 4 (75%), оценка 4; уходит в журнал.
    changed = (await client.patch(url, json={"points": [[3, 1]], "title": "Входная работа", "deadline": None},
                                  headers=bearer(teacher))).json()
    assert (changed["title"], changed["max_score"], changed["deadline"]) == ("Входная работа", 4, None)
    mine = (await client.get(f"/attempts/{attempt['id']}", headers=student(olya))).json()
    assert (mine["score"], mine["max_score"], mine["grade"]) == (3, 4, 4)
    graded = [e["data"] for e in await outbox("assessment.attempt.graded")]
    assert graded[-1]["grade"] == 4
    # Критерии строже — оценка пересчитана.
    await client.patch(url, json={"grade_scale": {"five": 90, "four": 80, "three": 50}}, headers=bearer(teacher))
    assert (await client.get(f"/attempts/{attempt['id']}", headers=student(olya))).json()["grade"] == 3
    parts = (await client.get(f"{url}/parts", headers=bearer(teacher))).json()
    assert [(p["variant"], [i["points"] for i in p["items"]], p["test_points"]) for p in parts] == [(None, [3, 1], [1, 1])]
    # Баллы из теста (там по 1) — обратно 1 из 2.
    back = (await client.patch(url, json={"points_from_tests": True}, headers=bearer(teacher))).json()
    assert back["max_score"] == 2


async def test_lists_paged_and_filtered(client, fakes):
    """Списки тестов и выданных работ — постранично, с фильтром по классу на сервере; кому назначали — отдельно."""
    teacher, olya, petya = uuid4(), uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    tests = [await make_test(client, teacher, tasks[:1], title=f"Тест {n}", grade_level=7 if n % 2 else 8) for n in range(5)]
    await link(teacher, olya)
    await link(teacher, petya)
    for t in tests:
        await assign(client, teacher, t, target_type="student", target_id=str(olya if t["grade_level"] == 7 else petya))
    page = (await client.get("/tests", params={"limit": 2, "offset": 2}, headers=bearer(teacher))).json()
    assert [t["title"] for t in page] == ["Тест 2", "Тест 1"]  # новые первыми
    assert len((await client.get("/tests", params={"grade_level": "7"}, headers=bearer(teacher))).json()) == 2
    assert len((await client.get("/tests", headers=bearer(teacher))).json()) == 5  # без limit — все
    given = (await client.get("/assignments", params={"role": "teacher", "limit": 3}, headers=bearer(teacher))).json()
    rest = (await client.get("/assignments", params={"role": "teacher", "limit": 3, "offset": 3}, headers=bearer(teacher))).json()
    assert (len(given), len(rest)) == (3, 2) and not {a["id"] for a in given} & {a["id"] for a in rest}
    eighth = (await client.get("/assignments", params={"role": "teacher", "grade_level": "8"}, headers=bearer(teacher))).json()
    assert {a["target_id"] for a in eighth} == {str(petya)} and len(eighth) == 3
    targets = (await client.get("/assignments/targets", headers=bearer(teacher))).json()
    assert {t["target_id"] for t in targets} == {str(olya), str(petya)}


async def test_lesson_deleted_unlinks_homework(client, fakes):
    """Занятие удалили из расписания — ДЗ к нему остаётся, привязка к уроку снимается (решение №54)."""
    teacher, olya = uuid4(), uuid4()
    tasks = await make_tasks(client, teacher)
    test = await make_test(client, teacher, tasks[:1])
    await link(teacher, olya)
    lesson = str(uuid4())
    fakes.lessons[lesson] = str(teacher)
    a = await assign(client, teacher, test, kind="homework", target_type="student", target_id=str(olya), lesson_id=lesson)
    await apply(handlers.on_schedule_event, "schedule.lesson.deleted", lesson_ids=[lesson])
    after = (await client.get(f"/assignments/{a['id']}", headers=bearer(teacher))).json()
    assert after["lesson_id"] is None and after["kind"] == "homework"
