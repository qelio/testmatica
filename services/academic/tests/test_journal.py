from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from .conftest import add_person, bearer, outbox


def period(days_from=-30, days_to=30) -> dict:
    now = datetime.now(UTC)
    return {"from": (now + timedelta(days=days_from)).isoformat(), "to": (now + timedelta(days=days_to)).isoformat()}


async def grade_type_id(client, teacher, name="Работа на уроке") -> str:
    types = (await client.get("/grade-types", headers=bearer(teacher))).json()
    return next(t["id"] for t in types if t["name"] == name)


async def put_grade(client, teacher, lesson, student, value, type_id, comment="Молодец"):
    return await client.post(
        f"/lessons/{lesson}/grades",
        json={"student_id": str(student), "value": value, "grade_type_id": type_id, "comment": comment},
        headers=bearer(teacher),
    )


@pytest.fixture
async def setup(world):
    teacher, anya, petya = uuid4(), uuid4(), uuid4()
    await add_person(teacher, "Мария Ивановна", ("teacher",))
    await add_person(anya, "Аня")
    await add_person(petya, "Петя")
    gid = world.group(teacher, [anya, petya])
    past1 = world.lesson(teacher, [anya, petya], -7, group_id=gid)
    past2 = world.lesson(teacher, [anya, petya], -2, group_id=gid)
    future = world.lesson(teacher, [anya, petya], 3, group_id=gid)
    return {"teacher": teacher, "anya": anya, "petya": petya, "gid": gid, "past1": past1, "past2": past2, "future": future}


async def test_journal_grades_attendance_and_stats(client, world, setup):
    t, anya, petya = setup["teacher"], setup["anya"], setup["petya"]
    type_id = await grade_type_id(client, t)

    assert (await put_grade(client, t, setup["past1"], anya, 5, type_id)).status_code == 201
    assert (await put_grade(client, t, setup["past1"], anya, 4, type_id, "Хорошо, но с ошибкой")).status_code == 201
    assert (await put_grade(client, t, setup["past2"], petya, 3, type_id)).status_code == 201

    assert (await client.post(f"/lessons/{setup['past1']}/attendance/all-present", headers=bearer(t))).status_code == 204
    r = await client.put(f"/lessons/{setup['past2']}/attendance/{petya}", json={"status": "late"}, headers=bearer(t))
    assert r.status_code == 204
    await client.put(f"/lessons/{setup['past2']}/attendance/{anya}", json={"status": "sick"}, headers=bearer(t))

    j = (await client.get("/journal", params={"group_id": str(setup["gid"]), **period()}, headers=bearer(t))).json()
    assert j["title"] == "7А"
    assert [lesson["started"] for lesson in j["lessons"]] == [True, True, False]
    assert [s["full_name"] for s in j["students"]] == ["Аня", "Петя"]
    stats = {s["full_name"]: s["stats"] for s in j["students"]}
    assert stats["Аня"]["average"] == 4.5 and stats["Аня"]["attendance_rate"] == 0.5 and stats["Аня"]["sick"] == 1
    assert stats["Петя"]["average"] == 3 and stats["Петя"]["attendance_rate"] == 1.0
    assert j["stats"]["average"] == 4.0 and j["stats"]["grades_count"] == 3
    assert len(j["attendance"]) == 4
    assert j["grades"][0]["grade_type"] == "Работа на уроке"

    created = await outbox("academic.grade.created")
    assert created[0]["data"]["teacher_name"] == "Мария Ивановна" and created[0]["data"]["value"] == 5


async def test_grade_validation(client, world, setup):
    t, anya = setup["teacher"], setup["anya"]
    type_id = await grade_type_id(client, t)

    blank = await put_grade(client, t, setup["past1"], anya, 5, type_id, "   ")
    assert blank.status_code == 422
    assert (await put_grade(client, t, setup["past1"], anya, 6, type_id)).status_code == 422
    future = await put_grade(client, t, setup["future"], anya, 5, type_id)
    assert future.json()["error"]["code"] == "lesson_not_started"
    stranger = await put_grade(client, t, setup["past1"], uuid4(), 5, type_id)
    assert stranger.json()["error"]["code"] == "student_not_found"
    other_teacher = await put_grade(client, uuid4(), setup["past1"], anya, 5, type_id)
    assert other_teacher.status_code == 404

    cancelled = world.lesson(t, [anya], -1, group_id=setup["gid"], status="cancelled")
    assert (await put_grade(client, t, cancelled, anya, 5, type_id)).json()["error"]["code"] == "lesson_cancelled"
    # Отменённые занятия не попадают в журнал.
    j = (await client.get("/journal", params={"group_id": str(setup["gid"]), **period()}, headers=bearer(t))).json()
    assert str(cancelled) not in [lesson["id"] for lesson in j["lessons"]]


async def test_update_and_delete_grade(client, world, setup):
    t, anya = setup["teacher"], setup["anya"]
    type_id = await grade_type_id(client, t)
    test_type = await grade_type_id(client, t, "Контрольная работа")
    grade = (await put_grade(client, t, setup["past1"], anya, 3, type_id)).json()

    upd = await client.patch(
        f"/grades/{grade['id']}", json={"value": 4, "grade_type_id": test_type, "comment": "Исправил"}, headers=bearer(t)
    )
    assert upd.status_code == 200
    assert (upd.json()["value"], upd.json()["grade_type"], upd.json()["comment"]) == (4, "Контрольная работа", "Исправил")

    assert (await client.patch(f"/grades/{grade['id']}", json={"value": 5}, headers=bearer(uuid4()))).status_code == 404
    assert (await client.delete(f"/grades/{grade['id']}", headers=bearer(uuid4()))).status_code == 404
    assert (await client.delete(f"/grades/{grade['id']}", headers=bearer(t))).status_code == 204
    assert len(await outbox("academic.grade.deleted")) == 1


async def test_attendance_clear_and_all_present_keeps_marks(client, world, setup):
    t, anya, petya = setup["teacher"], setup["anya"], setup["petya"]
    await client.put(f"/lessons/{setup['past1']}/attendance/{anya}", json={"status": "absent"}, headers=bearer(t))
    await client.post(f"/lessons/{setup['past1']}/attendance/all-present", headers=bearer(t))
    j = (await client.get("/journal", params={"group_id": str(setup["gid"]), **period()}, headers=bearer(t))).json()
    marks = {a["student_id"]: a["status"] for a in j["attendance"]}
    assert marks == {str(anya): "absent", str(petya): "present"}

    await client.put(f"/lessons/{setup['past1']}/attendance/{anya}", json={"status": None}, headers=bearer(t))
    j = (await client.get("/journal", params={"group_id": str(setup["gid"]), **period()}, headers=bearer(t))).json()
    assert {a["student_id"] for a in j["attendance"]} == {str(petya)}

    future = await client.put(f"/lessons/{setup['future']}/attendance/{anya}", json={"status": "present"}, headers=bearer(t))
    assert future.status_code == 409


async def test_left_student_with_records_stays_in_journal(client, world, setup):
    t, anya, petya = setup["teacher"], setup["anya"], setup["petya"]
    type_id = await grade_type_id(client, t)
    await put_grade(client, t, setup["past1"], petya, 4, type_id)
    world.groups[str(setup["gid"])]["member_ids"] = [str(anya)]  # Петя ушёл из группы
    j = (await client.get("/journal", params={"group_id": str(setup["gid"]), **period()}, headers=bearer(t))).json()
    assert [(s["full_name"], s["current"]) for s in j["students"]] == [("Аня", True), ("Петя", False)]


async def test_individual_journal(client, world):
    t, sid = uuid4(), uuid4()
    await add_person(sid, "Оля")
    world.links.add((str(t), str(sid)))
    world.lesson(t, [sid], -1, student_id=sid, subject="Физика")
    j = (await client.get("/journal", params={"student_id": str(sid), **period()}, headers=bearer(t))).json()
    assert j["title"] == "Оля" and len(j["lessons"]) == 1

    assert (await client.get("/journal", params={"student_id": str(uuid4()), **period()}, headers=bearer(t))).status_code == 404
    both = await client.get("/journal", params=period(), headers=bearer(t))
    assert both.status_code == 422


async def test_student_sees_own_grades_by_subject(client, world):
    t1, t2, sid = uuid4(), uuid4(), uuid4()
    await add_person(t1, "Мария Ивановна", ("teacher",))
    await add_person(t2, "Иван Петрович", ("teacher",))
    algebra = world.lesson(t1, [sid], -3, student_id=sid, subject="Алгебра")
    physics = world.lesson(t2, [sid], -2, student_id=sid, subject="Физика")
    type_id = await grade_type_id(client, t1)
    await put_grade(client, t1, algebra, sid, 5, type_id)
    await put_grade(client, t1, algebra, sid, 3, type_id)
    await put_grade(client, t2, physics, sid, 4, type_id)
    await client.put(f"/lessons/{physics}/attendance/{sid}", json={"status": "absent"}, headers=bearer(t2))

    mine = (await client.get("/me/grades", params=period(), headers=bearer(sid, ("student",)))).json()
    subjects = {s["subject"]: s for s in mine["subjects"]}
    assert subjects["Алгебра"]["stats"]["average"] == 4.0
    assert subjects["Алгебра"]["teacher_names"] == ["Мария Ивановна"]
    assert subjects["Физика"]["stats"]["attendance_rate"] == 0.0
    assert mine["stats"]["grades_count"] == 3

    # Педагог не может смотреть «мои оценки», ученик — журнал.
    assert (await client.get("/me/grades", params=period(), headers=bearer(t1))).status_code == 403
    assert (await client.get("/journal", params={"student_id": str(sid), **period()}, headers=bearer(sid, ("student",)))).status_code == 403


async def test_grade_types_managed_by_moderator(client, world, setup):
    t = setup["teacher"]
    moderator = bearer(uuid4(), ("moderator",))
    defaults = (await client.get("/grade-types", headers=bearer(t))).json()
    assert [x["name"] for x in defaults][:2] == ["Работа на уроке", "Домашняя работа"]

    assert (await client.post("/grade-types", json={"name": "Тестовый"}, headers=bearer(t))).status_code == 403
    created = await client.post("/grade-types", json={"name": "Тестовый", "position": 10}, headers=moderator)
    assert created.status_code == 201
    dup = await client.post("/grade-types", json={"name": "Тестовый"}, headers=moderator)
    assert dup.status_code == 409

    off = await client.patch(f"/grade-types/{created.json()['id']}", json={"is_active": False}, headers=moderator)
    assert off.json()["is_active"] is False
    assert "Тестовый" not in [x["name"] for x in (await client.get("/grade-types", headers=bearer(t))).json()]
    assert "Тестовый" in [x["name"] for x in (await client.get("/grade-types?all=true", headers=moderator)).json()]
    used = await put_grade(client, t, setup["past1"], setup["anya"], 5, created.json()["id"])
    assert used.json()["error"]["code"] == "invalid_grade_type"
