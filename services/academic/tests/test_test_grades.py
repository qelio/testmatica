from datetime import UTC, datetime
from uuid import uuid4

from testmatica_common.testing import make_envelope

from app import test_grades
from app.deps import db

from .conftest import add_person, bearer, outbox
from .test_journal import grade_type_id, period


async def graded(**data) -> None:
    async with db.sessionmaker() as s, s.begin():
        await test_grades.on_assessment_event(make_envelope("assessment.attempt.graded", data), s)


async def test_grade_from_test_goes_to_journal(client, world):
    """Оценка за работу — отдельной колонкой журнала, без привязки к уроку (решение №34)."""
    teacher, pupil = uuid4(), uuid4()
    await add_person(teacher, "Мария Ивановна", ("teacher",))
    group = world.group(teacher, [pupil])
    lesson = world.lesson(teacher, [pupil], days=-1, group_id=group)
    type_id = await grade_type_id(client, teacher, "Контрольная работа")
    assignment = str(uuid4())
    base = {"attempt_id": str(uuid4()), "assignment_id": assignment, "student_id": str(pupil), "teacher_id": str(teacher),
            "title": "Дроби", "subject": "Алгебра", "kind": "homework", "score": 5, "max_score": 6, "percent": 83.3, "grade": 4,
            "to_journal": True, "lesson_id": str(lesson), "group_id": str(group), "grade_type_id": type_id,
            "assigned_at": datetime.now(UTC).isoformat()}

    await graded(**base | {"to_journal": False})  # педагог не просил — журнал не трогаем
    assert await outbox("academic.grade.created") == []

    await graded(**base)
    journal = (await client.get("/journal", params={"group_id": str(group), **period()}, headers=bearer(teacher))).json()
    [grade] = journal["grades"]
    assert grade["value"] == 4 and grade["source"] == "test" and grade["comment"] == "ДЗ «Дроби»: 83.3% (5 из 6)"
    assert grade["lesson_id"] is None and grade["work_id"] == assignment  # не в колонке урока
    assert [(w["id"], w["title"]) for w in journal["works"]] == [(assignment, "Дроби")]
    assert (await outbox("academic.grade.created"))[0]["data"]["value"] == 4

    # Переназначили, пересдал лучше — оценка обновилась, а не задвоилась.
    await graded(**base | {"attempt_id": str(uuid4()), "score": 6, "percent": 100.0, "grade": 5})
    journal = (await client.get("/journal", params={"group_id": str(group), **period()}, headers=bearer(teacher))).json()
    assert [(g["value"], g["comment"]) for g in journal["grades"]] == [(5, "ДЗ «Дроби»: 100% (6 из 6)")]

    # Педагог исправил оценку вручную — та же колонка, в комментарии видно, что оценку поставил он.
    await graded(**base | {"grade": 3, "by_teacher": True})
    journal = (await client.get("/journal", params={"group_id": str(group), **period()}, headers=bearer(teacher))).json()
    assert [(g["value"], g["comment"]) for g in journal["grades"]] == [(3, "ДЗ «Дроби»: 83.3% (5 из 6), оценку поставил педагог")]

    # Работа, выданная лично ученику, — в его журнале, а не в журнале группы.
    own = str(uuid4())
    await graded(**base | {"assignment_id": own, "group_id": None, "title": "Лично"})
    journal = (await client.get("/journal", params={"group_id": str(group), **period()}, headers=bearer(teacher))).json()
    assert [w["title"] for w in journal["works"]] == ["Дроби"]
    world.links.add((str(teacher), str(pupil)))
    personal = (await client.get("/journal", params={"student_id": str(pupil), **period()}, headers=bearer(teacher))).json()
    assert [w["title"] for w in personal["works"]] == ["Лично"]


async def test_grade_removed_with_assignment(client, world):
    """Работу удалили или убрали у ученика — оценка за неё из журнала тоже уходит."""
    teacher, pupil, other = uuid4(), uuid4(), uuid4()
    await add_person(teacher, "Иванова Мария", ("teacher",))
    group = world.group(teacher, [pupil, other])
    type_id = await grade_type_id(client, teacher, "Контрольная работа")
    assignment = str(uuid4())
    base = {"attempt_id": str(uuid4()), "assignment_id": assignment, "teacher_id": str(teacher), "title": "Дроби", "subject": "Алгебра", "kind": "test",
            "score": 5, "max_score": 6, "percent": 83.3, "grade": 4, "to_journal": True, "group_id": str(group),
            "grade_type_id": type_id, "assigned_at": datetime.now(UTC).isoformat()}
    await graded(**base | {"student_id": str(pupil)})
    await graded(**base | {"student_id": str(other)})
    journal = lambda: client.get("/journal", params={"group_id": str(group), **period()}, headers=bearer(teacher))  # noqa: E731
    assert len((await journal()).json()["grades"]) == 2

    async with db.sessionmaker() as s, s.begin():
        await test_grades.on_assessment_event(make_envelope("assessment.assignment.students_removed", {
            "assignment_id": assignment, "teacher_id": str(teacher), "title": "Дроби", "student_ids": [str(pupil)]}), s)
    assert [g["student_id"] for g in (await journal()).json()["grades"]] == [str(other)]
    async with db.sessionmaker() as s, s.begin():
        await test_grades.on_assessment_event(make_envelope("assessment.assignment.deleted", {
            "assignment_id": assignment, "teacher_id": str(teacher), "title": "Дроби", "student_ids": [str(other)]}), s)
    body = (await journal()).json()
    assert body["grades"] == [] and body["works"] == []
    assert len(await outbox("academic.grade.deleted")) == 2


async def test_deleted_lesson_removed_from_journal(client, world):
    """Занятие удалили из расписания — его оценки и посещаемость уходят из журнала, другие — остаются (решение №54)."""
    from uuid import UUID

    from sqlalchemy import func, select

    from app import schedule_sync
    from app.models import Attendance, Grade

    teacher, pupil = uuid4(), uuid4()
    type_id = await grade_type_id(client, teacher, "Работа на уроке")
    gone, kept = uuid4(), uuid4()
    now = datetime.now(UTC)
    async with db.sessionmaker() as s, s.begin():
        for lesson in (gone, kept):
            s.add(Grade(teacher_id=teacher, student_id=pupil, lesson_id=lesson, lesson_starts_at=now, value=5,
                        grade_type_id=UUID(type_id), comment="Ответ у доски"))
            s.add(Attendance(lesson_id=lesson, student_id=pupil, teacher_id=teacher, lesson_starts_at=now, status="present"))
    async with db.sessionmaker() as s, s.begin():
        await schedule_sync.on_schedule_event(make_envelope("schedule.lesson.deleted", {"lesson_ids": [str(gone)]}), s)
    async with db.sessionmaker() as s:
        grades = (await s.execute(select(Grade.lesson_id))).scalars().all()
        visits = await s.scalar(select(func.count()).select_from(Attendance))
    assert grades == [kept] and visits == 1


async def test_subject_journals_shared_with_colleague(client, world):
    """Журналы класса по предметам; журнал общий с коллегой: видны занятия и оценки обоих, менять — только свои (решение №59)."""
    import httpx

    from app.deps import assessment

    maria, petr, pupil = uuid4(), uuid4(), uuid4()
    await add_person(maria, "Иванова Мария", ("teacher",))
    await add_person(petr, "Петров Пётр", ("teacher",))
    group = world.group(maria, [pupil])
    world.shares.add((str(group), str(petr)))
    algebra = world.lesson(maria, [pupil], days=-2, group_id=group)
    informatics = world.lesson(petr, [pupil], days=-1, group_id=group, subject="Информатика")
    type_id = await grade_type_id(client, maria, "Работа на уроке")
    grade = {"student_id": str(pupil), "value": 5, "grade_type_id": type_id, "comment": "Ответ у доски"}
    assert (await client.post(f"/lessons/{algebra}/grades", json=grade, headers=bearer(maria))).status_code == 201
    mine = (await client.post(f"/lessons/{informatics}/grades", json=grade | {"value": 4}, headers=bearer(petr))).json()
    # Пётр не может ставить оценки на занятии Марии.
    assert (await client.post(f"/lessons/{algebra}/grades", json=grade, headers=bearer(petr))).status_code == 404
    # Оценка за тест по информатике без урока — в журнал информатики; старая без предмета — в «Без предмета».
    base = {"attempt_id": str(uuid4()), "student_id": str(pupil), "teacher_id": str(petr), "kind": "test", "score": 3,
            "max_score": 3, "percent": 100.0, "grade": 5, "to_journal": True, "group_id": str(group), "grade_type_id": type_id,
            "assigned_at": datetime.now(UTC).isoformat()}
    await graded(**base | {"assignment_id": str(uuid4()), "title": "Циклы", "subject": "Информатика"})
    old = str(uuid4())
    await graded(**base | {"assignment_id": old, "title": "Старый", "subject": None})

    get = lambda who, **q: client.get("/journal", params={"group_id": str(group), **period(), **q}, headers=bearer(who))  # noqa: E731
    body = (await get(maria)).json()
    assert body["subjects"] == ["Алгебра", "Информатика", None] and body["subject"] == "Алгебра"  # предмет класса — первым
    assert [(g["value"], g["own"]) for g in body["grades"]] == [(5, True)]
    body = (await get(maria, subject="Информатика")).json()
    assert [(lesson["own"], lesson["teacher_name"]) for lesson in body["lessons"]] == [(False, "Петров Пётр")]
    assert sorted((g["value"], g["own"], g["teacher_name"]) for g in body["grades"]) == [(4, False, "Петров Пётр"), (5, False, "Петров Пётр")]
    assert [w["title"] for w in body["works"]] == ["Циклы"]
    assert [w["title"] for w in (await get(petr, subject="")).json()["works"]] == ["Старый"]
    # Владелец класса меняет любые оценки журнала класса (решение №61); Пётр без права — только свои.
    maria_grade = next(g for g in (await get(maria)).json()["grades"] if g["own"])
    assert (await client.patch(f"/grades/{maria_grade['id']}", json={"value": 2}, headers=bearer(petr))).status_code == 404
    petr_view = (await get(petr, subject="Алгебра")).json()["grades"]
    assert [g["can_edit"] for g in petr_view] == [False]
    assert (await client.patch(f"/grades/{mine['id']}", json={"value": 3}, headers=bearer(maria))).json()["value"] == 3
    world.share_perms[(str(group), str(petr))] = ["journal_all"]  # дали право «правка всех оценок»
    assert (await client.patch(f"/grades/{maria_grade['id']}", json={"value": 4}, headers=bearer(petr))).json()["value"] == 4

    # Разноска старых оценок: предмет — у работы в assessment.
    assessment.transport = httpx.MockTransport(lambda r: httpx.Response(200, json={old: "Информатика"}))
    await test_grades.backfill_subjects()
    assert [w["title"] for w in (await get(petr, subject="Информатика")).json()["works"]] == ["Циклы", "Старый"]
