from uuid import uuid4

from .conftest import CHOICE, CODE, LONG, MULTI, SHORT, bearer, link, outbox, run_code_checks, student


async def published(client, body):
    author = uuid4()
    task = (await client.post("/tasks", json=body, headers=bearer(author, ("moderator",)))).json()
    await client.post(f"/tasks/{task['id']}/submit", headers=bearer(author, ("moderator",)))
    return task, author


async def answer(client, task, who, headers=None, context=None, **ans):
    return await client.post(
        f"/tasks/{task['id']}/submissions",
        json={"context_type": "practice", "context_id": str(context or CTX), "answer": ans},
        headers=headers or student(who),
    )


CTX = uuid4()  # «материал в модуле курса»


async def test_choice_single_and_multiple(client):
    task, _ = await published(client, CHOICE)
    pupil = uuid4()
    opts = task["options"]
    wrong = await answer(client, task, pupil, option_ids=[opts[1]["id"]])
    assert wrong.json()["status"] == "incorrect" and wrong.json()["score"] == 0
    right = await answer(client, task, pupil, option_ids=[opts[0]["id"]])
    assert right.json()["status"] == "correct"
    bogus = await answer(client, task, pupil, option_ids=[str(uuid4())])
    assert bogus.status_code == 422

    multi, _ = await published(client, MULTI)
    assert multi["multiple"] is True
    o = multi["options"]
    assert (await answer(client, multi, pupil, option_ids=[o[0]["id"]])).json()["status"] == "incorrect"
    assert (await answer(client, multi, pupil, option_ids=[o[0]["id"], o[2]["id"]])).json()["status"] == "correct"


async def test_solve_view_hides_key_and_opens_explanation(client):
    task, _ = await published(client, CHOICE)
    pupil = uuid4()
    view = (await client.get(f"/tasks/{task['id']}/solve", params={"context_id": str(CTX)}, headers=student(pupil))).json()
    assert view["solved"] is False and view["explanation"] is None and view["submissions"] == []
    assert all(o["is_correct"] is None for o in view["task"]["options"])
    # Даже педагог в режиме решения не видит ответы.
    teacher_view = (await client.get(f"/tasks/{task['id']}/solve", params={"context_id": str(CTX)}, headers=bearer(uuid4()))).json()
    assert all(o["is_correct"] is None for o in teacher_view["task"]["options"])

    wrong = task["options"][1]["id"]
    for _ in range(2):
        await answer(client, task, pupil, option_ids=[wrong])
    view = (await client.get(f"/tasks/{task['id']}/solve", params={"context_id": str(CTX)}, headers=student(pupil))).json()
    assert view["explanation"] is None and len(view["submissions"]) == 2
    await answer(client, task, pupil, option_ids=[wrong])  # третья попытка — разбор открывается
    view = (await client.get(f"/tasks/{task['id']}/solve", params={"context_id": str(CTX)}, headers=student(pupil))).json()
    assert view["explanation"] == "Переносим 6 и делим на 2."
    # Попытки в другом модуле — отдельно.
    other = (await client.get(f"/tasks/{task['id']}/solve", params={"context_id": str(uuid4())}, headers=student(pupil))).json()
    assert other["submissions"] == []


async def test_short_answer_normalization(client):
    task, _ = await published(client, SHORT)
    pupil = uuid4()
    for text, expected in [("3.5", "correct"), (" 3,50 ", "correct"), ("3.6", "incorrect"),
                           ("Три  с половиной", "correct"), ("три", "incorrect")]:
        assert (await answer(client, task, pupil, text=text)).json()["status"] == expected, text
    assert (await answer(client, task, pupil, text="   ")).status_code == 422


async def test_code_history_is_kept_for_teacher(client, fakes):
    task, _ = await published(client, CODE)
    teacher, pupil = uuid4(), uuid4()
    await link(teacher, pupil)

    first = (await answer(client, task, pupil, code="a, b = map(int, input().split())\nprint(a - b)")).json()
    assert first["status"] == "checking"
    second = (await answer(client, task, pupil, code="# correct\nprint(sum(map(int, input().split())))")).json()
    await run_code_checks()

    # Ученик видит только номер упавшего теста и вид ошибки, без протокола.
    mine = (await client.get(f"/submissions/{first['id']}", headers=student(pupil))).json()
    assert (mine["status"], mine["failed_case"], mine["failure"], mine["run_log"]) == ("incorrect", 2, "wrong_answer", None)
    assert (await client.get(f"/submissions/{second['id']}", headers=student(pupil))).json()["status"] == "correct"
    # В песочницу ушли тесты задачи и лимиты.
    assert fakes.runs[0]["tests"] == [{"input": "2 3", "expected": "5"}, {"input": "40 2", "expected": "42"}]
    assert (fakes.runs[0]["time_limit_s"], fakes.runs[0]["memory_limit_mb"]) == (1, 64)

    # Педагог видит всю историю: код каждой попытки и протокол прогона.
    history = (await client.get(f"/students/{pupil}/submissions", params={"task_id": task["id"]}, headers=bearer(teacher))).json()
    assert [h["answer"]["code"].splitlines()[-1] for h in history] == ["print(sum(map(int, input().split())))", "print(a - b)"]
    assert history[1]["run_log"][1]["output"] == "41"
    assert history[0]["task_title"] == task["title"] and history[0]["task_type"] == "code"
    # Чужой педагог — нет.
    assert (await client.get(f"/students/{pupil}/submissions", headers=bearer(uuid4()))).status_code == 404
    assert (await client.get(f"/submissions/{first['id']}", headers=bearer(uuid4()))).status_code == 404
    assert len(await outbox("assessment.submission.checked")) == 2


async def test_code_runner_down_marks_error(client, fakes):
    task, _ = await published(client, CODE)
    pupil = uuid4()
    fakes.runner_up = False
    sub = (await answer(client, task, pupil, code="print(1)")).json()
    await run_code_checks()
    assert (await client.get(f"/submissions/{sub['id']}", headers=student(pupil))).json()["status"] == "error"


async def test_long_answer_with_file_and_review(client, fakes):
    task, _ = await published(client, LONG)
    teacher, pupil = uuid4(), uuid4()
    await link(teacher, pupil)
    no_file = await answer(client, task, pupil, text="Предположим противное…")
    assert no_file.json()["error"]["code"] == "file_required"
    foreign = fakes.file(uuid4())
    stolen = await client.post(
        f"/tasks/{task['id']}/submissions",
        json={"context_type": "assignment", "context_id": str(CTX), "answer": {"text": "x"}, "file_ids": [foreign]},
        headers=student(pupil),
    )
    assert stolen.status_code == 422

    own = fakes.file(pupil, "доказательство.pdf")
    sub = (
        await client.post(
            f"/tasks/{task['id']}/submissions",
            json={"context_type": "assignment", "context_id": str(CTX), "answer": {"text": "Предположим противное…"}, "file_ids": [own]},
            headers=student(pupil),
        )
    ).json()
    assert sub["status"] == "pending_review"
    assert (sub["files"][0]["filename"], sub["files"][0]["url"]) == ("доказательство.pdf", f"http://s3/{own}")

    denied = await client.post(f"/submissions/{sub['id']}/review", json={"score": 1, "comment": "Верно"}, headers=bearer(uuid4()))
    assert denied.status_code == 404
    reviewed = await client.post(
        f"/submissions/{sub['id']}/review", json={"score": 0.8, "comment": "Верно, но не хватает вывода"}, headers=bearer(teacher)
    )
    assert (reviewed.json()["status"], reviewed.json()["score"]) == ("reviewed", 0.8)
    event = (await outbox("assessment.submission.reviewed"))[0]["data"]
    assert event["task_title"] == "Доказательство" and event["comment"] == "Верно, но не хватает вывода"


async def test_guest_sees_statement_but_cannot_answer(client):
    task, _ = await published(client, CHOICE)
    assert (await client.get(f"/tasks/{task['id']}/solve", params={"context_id": str(CTX)})).status_code == 200
    resp = await client.post(
        f"/tasks/{task['id']}/submissions", json={"context_id": str(CTX), "answer": {"option_ids": []}}
    )
    assert resp.status_code == 401
