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
            "title": "Дроби", "kind": "homework", "score": 5, "max_score": 6, "percent": 83.3, "grade": 4,
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
    base = {"attempt_id": str(uuid4()), "assignment_id": assignment, "teacher_id": str(teacher), "title": "Дроби", "kind": "test",
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
