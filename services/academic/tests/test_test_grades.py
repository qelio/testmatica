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
    teacher, pupil = uuid4(), uuid4()
    await add_person(teacher, "Мария Ивановна", ("teacher",))
    group = world.group(teacher, [pupil])
    lesson = world.lesson(teacher, [pupil], days=-1, group_id=group)
    type_id = await grade_type_id(client, teacher, "Контрольная работа")
    assignment = str(uuid4())
    base = {"attempt_id": str(uuid4()), "assignment_id": assignment, "student_id": str(pupil), "teacher_id": str(teacher),
            "title": "Дроби", "kind": "homework", "score": 5, "max_score": 6, "percent": 83.3, "grade": 4,
            "to_journal": True, "lesson_id": str(lesson), "grade_type_id": type_id}

    await graded(**base | {"to_journal": False})  # педагог не просил — журнал не трогаем
    assert await outbox("academic.grade.created") == []

    await graded(**base)
    journal = (await client.get("/journal", params={"group_id": str(group), **period()}, headers=bearer(teacher))).json()
    [grade] = journal["grades"]
    assert grade["value"] == 4 and grade["source"] == "test" and grade["comment"] == "ДЗ «Дроби»: 83.3% (5 из 6)"
    assert (await outbox("academic.grade.created"))[0]["data"]["value"] == 4

    # Переназначили, пересдал лучше — оценка обновилась, а не задвоилась.
    await graded(**base | {"attempt_id": str(uuid4()), "score": 6, "percent": 100.0, "grade": 5})
    journal = (await client.get("/journal", params={"group_id": str(group), **period()}, headers=bearer(teacher))).json()
    assert [(g["value"], g["comment"]) for g in journal["grades"]] == [(5, "ДЗ «Дроби»: 100% (6 из 6)")]

    # Урок удалён — оценку пропускаем без ошибки.
    await graded(**base | {"assignment_id": str(uuid4()), "lesson_id": str(uuid4())})
