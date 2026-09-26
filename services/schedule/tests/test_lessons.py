from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError
from testmatica_common.testing import make_envelope

from app import handlers
from app.deps import db
from app.models import Lesson, ScheduledJob

from .conftest import add_person, bearer, outbox, student_bearer


def at(days: int, hour: int = 10, minute: int = 0) -> datetime:
    base = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days)
    return base.replace(hour=hour, minute=minute)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def window(days_from=-1, days_to=60) -> dict:
    return {"from": iso(at(days_from, 0)), "to": iso(at(days_to, 0))}


async def create(client, teacher, **body):
    resp = await client.post("/lessons", json=body, headers=bearer(teacher))
    return resp


async def individual(client, teacher, fake, student=None, start=None, duration=60, **extra):
    student = student or uuid4()
    fake.link(teacher, student)
    resp = await create(
        client, teacher, kind="individual", student_id=str(student), starts_at=iso(start or at(3)),
        duration_min=duration, **extra,
    )
    assert resp.status_code == 201, resp.text
    return student, resp.json()["lessons"][0]


async def test_individual_lesson_visibility(client, teacher, fake_classroom):
    student, lesson = await individual(client, teacher, fake_classroom, subject="Физика")
    await add_person(student, "Петя")
    assert lesson["kind"] == "individual" and lesson["duration_min"] == 60

    mine = (await client.get("/lessons", params=window(), headers=bearer(teacher))).json()
    assert [(item["title"], item["subject"]) for item in mine] == [("Петя", "Физика")]
    assert mine[0]["participants"] == [{"id": str(student), "full_name": "Петя"}]

    theirs = (await client.get("/lessons", params=window(), headers=student_bearer(student))).json()
    assert theirs[0]["teacher"]["full_name"] == "Мария Ивановна"
    assert theirs[0]["title"] == "Мария Ивановна"  # ученику — имя педагога, а не своё
    assert theirs[0]["participants"] is None

    stranger = (await client.get("/lessons", params=window(), headers=student_bearer(uuid4()))).json()
    assert stranger == []
    assert (await client.get(f"/lessons/{lesson['id']}", headers=student_bearer(uuid4()))).status_code == 404


async def test_group_series(client, teacher, fake_classroom):
    s1, s2 = uuid4(), uuid4()
    gid = fake_classroom.group(teacher, [s1, s2])
    resp = await create(
        client, teacher, kind="group", group_id=str(gid), starts_at=iso(at(1, 9)), duration_min=45,
        repeat={"weekdays": [], "interval_weeks": 1, "count": 4}, timezone="Europe/Moscow",
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["count"] == 4
    assert resp.json()["lessons"][0]["title"] == "7А"
    assert resp.json()["lessons"][0]["subject"] == "Алгебра"  # из группы

    lessons = (await client.get("/lessons", params=window(), headers=student_bearer(s2))).json()
    assert len(lessons) == 4
    assert len({item["series_id"] for item in lessons}) == 1

    created = await outbox("schedule.lesson.created")
    assert len(created) == 1 and created[0]["data"]["count"] == 4
    assert sorted(created[0]["data"]["student_ids"]) == sorted([str(s1), str(s2)])


async def test_access_checks(client, teacher, fake_classroom):
    stranger = await create(
        client, teacher, kind="individual", student_id=str(uuid4()), starts_at=iso(at(2)), duration_min=60
    )
    assert stranger.status_code == 404

    archived = fake_classroom.group(teacher, [], archived=True)
    resp = await create(client, teacher, kind="group", group_id=str(archived), starts_at=iso(at(2)), duration_min=60)
    assert resp.json()["error"]["code"] == "group_archived"

    other_teacher_group = fake_classroom.group(uuid4(), [])
    resp = await create(client, teacher, kind="group", group_id=str(other_teacher_group), starts_at=iso(at(2)), duration_min=60)
    assert resp.status_code == 404

    student = await client.post("/lessons", json={}, headers=student_bearer(uuid4()))
    assert student.status_code == 403


async def test_conflicts(client, teacher, fake_classroom):
    await individual(client, teacher, fake_classroom, start=at(3, 10), duration=60)

    sid = uuid4()
    fake_classroom.link(teacher, sid)
    overlap = await create(client, teacher, kind="individual", student_id=str(sid), starts_at=iso(at(3, 10, 30)), duration_min=60)
    assert overlap.status_code == 409
    assert overlap.json()["error"]["code"] == "lesson_conflict"
    assert len(overlap.json()["error"]["details"]["conflicts"]) == 1

    # Встык — можно.
    adjacent = await create(client, teacher, kind="individual", student_id=str(sid), starts_at=iso(at(3, 11)), duration_min=30)
    assert adjacent.status_code == 201

    # Серия, одно из занятий которой пересекается, не создаётся целиком.
    series = await create(
        client, teacher, kind="individual", student_id=str(sid), starts_at=iso(at(3, 10) - timedelta(days=7)),
        duration_min=60, repeat={"interval_weeks": 1, "count": 3}, timezone="UTC",
    )
    assert series.status_code == 409
    assert len((await client.get("/lessons", params=window(-10, 30), headers=bearer(teacher))).json()) == 2


async def test_database_blocks_overlap_even_without_precheck(client, teacher, fake_classroom):
    _, lesson = await individual(client, teacher, fake_classroom, start=at(4, 12))
    with pytest.raises(IntegrityError, match="no_teacher_overlap"):
        async with db.sessionmaker() as s, s.begin():
            s.add(
                Lesson(
                    teacher_id=teacher, kind="individual", student_id=uuid4(),
                    starts_at=at(4, 12, 30), ends_at=at(4, 13, 30),
                )
            )
    # Отменённое занятие время не занимает.
    await client.post(f"/lessons/{lesson['id']}/cancel", json={}, headers=bearer(teacher))
    async with db.sessionmaker() as s, s.begin():
        s.add(Lesson(teacher_id=teacher, kind="individual", student_id=uuid4(),
                     starts_at=at(4, 12, 30), ends_at=at(4, 13, 30)))


async def test_update_following_and_cancel_following(client, teacher, fake_classroom):
    sid = uuid4()
    fake_classroom.link(teacher, sid)
    await create(
        client, teacher, kind="individual", student_id=str(sid), starts_at=iso(at(1, 10)), duration_min=60,
        repeat={"interval_weeks": 1, "count": 4}, timezone="UTC",
    )
    lessons = (await client.get("/lessons", params=window(), headers=bearer(teacher))).json()
    third = lessons[2]

    resp = await client.patch(
        f"/lessons/{third['id']}",
        json={"scope": "following", "subject": "Геометрия", "starts_at": iso(at(15, 12)), "duration_min": 90},
        headers=bearer(teacher),
    )
    assert resp.status_code == 200, resp.text
    lessons = (await client.get("/lessons", params=window(), headers=bearer(teacher))).json()
    assert [(item["subject"], item["starts_at"][11:16], item["duration_min"]) for item in lessons] == [
        (None, "10:00", 60), (None, "10:00", 60), ("Геометрия", "12:00", 90), ("Геометрия", "12:00", 90),
    ]

    await client.post(f"/lessons/{lessons[1]['id']}/cancel", json={"scope": "following"}, headers=bearer(teacher))
    statuses = [item["status"] for item in (await client.get("/lessons", params=window(), headers=bearer(teacher))).json()]
    assert statuses == ["scheduled", "cancelled", "cancelled", "cancelled"]
    cancelled = await outbox("schedule.lesson.cancelled")
    assert len(cancelled) == 1 and cancelled[0]["data"]["count"] == 3


async def test_teacher_reschedule_needs_student_confirmation(client, teacher, fake_classroom):
    student, lesson = await individual(client, teacher, fake_classroom, start=at(5, 10))
    resp = await client.post(
        f"/lessons/{lesson['id']}/reschedule", json={"starts_at": iso(at(6, 16))}, headers=bearer(teacher)
    )
    assert resp.status_code == 200
    pending = resp.json()["pending_reschedule"]
    assert pending["requested_by_me"] is True
    assert resp.json()["starts_at"] == lesson["starts_at"]  # время пока прежнее

    incoming = (await client.get("/reschedule-requests", headers=student_bearer(student))).json()
    assert incoming[0]["requested_by_me"] is False and incoming[0]["lesson"]["id"] == lesson["id"]
    # Автор запроса не может сам его подтвердить.
    assert (await client.post(f"/reschedule-requests/{pending['id']}/accept", headers=bearer(teacher))).status_code == 403

    ok = await client.post(f"/reschedule-requests/{pending['id']}/accept", headers=student_bearer(student))
    assert ok.status_code == 204
    moved = (await client.get(f"/lessons/{lesson['id']}", headers=bearer(teacher))).json()
    assert datetime.fromisoformat(moved["starts_at"]) == at(6, 16)
    assert moved["pending_reschedule"] is None
    assert len(await outbox("schedule.lesson.rescheduled")) == 1


async def test_student_declines_teacher_reschedule_cancels_lesson(client, teacher, fake_classroom):
    student, lesson = await individual(client, teacher, fake_classroom, start=at(5, 10))
    req = (
        await client.post(f"/lessons/{lesson['id']}/reschedule", json={"starts_at": iso(at(6, 16))}, headers=bearer(teacher))
    ).json()["pending_reschedule"]
    assert (await client.post(f"/reschedule-requests/{req['id']}/decline", headers=student_bearer(student))).status_code == 204
    after = (await client.get(f"/lessons/{lesson['id']}", headers=bearer(teacher))).json()
    assert after["status"] == "cancelled"
    assert after["cancel_reason"] == "Ученик не согласился с переносом"


async def test_student_proposes_teacher_declines(client, teacher, fake_classroom):
    student, lesson = await individual(client, teacher, fake_classroom, start=at(5, 10))
    resp = await client.post(
        f"/lessons/{lesson['id']}/reschedule",
        json={"starts_at": iso(at(5, 18)), "comment": "Не успеваю из школы"},
        headers=student_bearer(student),
    )
    req = resp.json()["pending_reschedule"]
    assert req["comment"] == "Не успеваю из школы"
    assert (await client.post(f"/reschedule-requests/{req['id']}/decline", headers=bearer(teacher))).status_code == 204
    after = (await client.get(f"/lessons/{lesson['id']}", headers=bearer(teacher))).json()
    assert after["status"] == "scheduled" and after["starts_at"] == lesson["starts_at"]


async def test_reschedule_into_busy_slot_is_rejected(client, teacher, fake_classroom):
    student, lesson = await individual(client, teacher, fake_classroom, start=at(5, 10))
    await individual(client, teacher, fake_classroom, start=at(5, 14))
    resp = await client.post(
        f"/lessons/{lesson['id']}/reschedule", json={"starts_at": iso(at(5, 14, 30))}, headers=student_bearer(student)
    )
    assert resp.status_code == 409


async def test_group_reschedule_is_immediate_and_teacher_only(client, teacher, fake_classroom):
    s1 = uuid4()
    gid = fake_classroom.group(teacher, [s1])
    lesson = (await create(client, teacher, kind="group", group_id=str(gid), starts_at=iso(at(2, 9)), duration_min=45)).json()["lessons"][0]
    denied = await client.post(f"/lessons/{lesson['id']}/reschedule", json={"starts_at": iso(at(2, 11))}, headers=student_bearer(s1))
    assert denied.status_code == 403
    moved = await client.post(f"/lessons/{lesson['id']}/reschedule", json={"starts_at": iso(at(2, 11))}, headers=bearer(teacher))
    assert moved.json()["pending_reschedule"] is None
    assert moved.json()["starts_at"][11:16] == "11:00"


async def test_classroom_events_update_future_lessons(client, teacher, fake_classroom):
    s1, newcomer = uuid4(), uuid4()
    gid = fake_classroom.group(teacher, [s1])
    await create(
        client, teacher, kind="group", group_id=str(gid), starts_at=iso(at(1, 9)), duration_min=45,
        repeat={"interval_weeks": 1, "count": 2}, timezone="UTC",
    )
    student, _ = await individual(client, teacher, fake_classroom, start=at(3, 15))

    async with db.sessionmaker() as s, s.begin():
        await handlers.on_classroom_event(
            make_envelope("classroom.member.added", {"group_id": str(gid), "teacher_id": str(teacher), "student_id": str(newcomer)}), s
        )
        await handlers.on_classroom_event(
            make_envelope("classroom.group.updated", {"group_id": str(gid), "teacher_id": str(teacher), "title": "8А"}), s
        )
    lessons = (await client.get("/lessons", params=window(), headers=student_bearer(newcomer))).json()
    assert [item["title"] for item in lessons] == ["8А", "8А"]

    async with db.sessionmaker() as s, s.begin():
        await handlers.on_classroom_event(
            make_envelope("classroom.member.removed", {"group_id": str(gid), "teacher_id": str(teacher), "student_id": str(newcomer)}), s
        )
        await handlers.on_classroom_event(
            make_envelope("classroom.link.ended", {"link_id": str(uuid4()), "teacher_id": str(teacher), "student_id": str(student)}), s
        )
    assert (await client.get("/lessons", params=window(), headers=student_bearer(newcomer))).json() == []
    individual_lesson = (await client.get("/lessons", params=window(), headers=student_bearer(student))).json()
    assert individual_lesson[0]["status"] == "cancelled"


async def test_reminders(client, teacher, fake_classroom):
    student, lesson = await individual(client, teacher, fake_classroom, start=datetime.now(UTC) + timedelta(hours=30))
    async with db.engine.connect() as conn:
        hours = sorted((await conn.execute(text("SELECT payload->>'hours' FROM scheduled_jobs"))).scalars())
    assert hours == ["2", "24"]

    # Время напоминания за 24 часа подошло.
    async with db.sessionmaker() as s, s.begin():
        await s.execute(
            update(ScheduledJob).where(ScheduledJob.payload["hours"].as_integer() == 24).values(run_at=datetime.now(UTC))
        )
    assert await handlers.run_due_jobs() == 1
    reminders = await outbox("schedule.lesson.reminder")
    assert reminders[0]["data"]["hours"] == 24 and reminders[0]["data"]["student_ids"] == [str(student)]

    # Занятие перенесли — старое напоминание за 2 часа не отправляется.
    await client.post(f"/lessons/{lesson['id']}/reschedule", json={"starts_at": iso(at(20, 10))}, headers=bearer(teacher))
    req = (await client.get("/reschedule-requests", headers=student_bearer(student))).json()[0]
    await client.post(f"/reschedule-requests/{req['id']}/accept", headers=student_bearer(student))
    old_start = datetime.fromisoformat(lesson["starts_at"])
    async with db.sessionmaker() as s, s.begin():
        await s.execute(
            update(ScheduledJob)
            .where(ScheduledJob.done_at.is_(None), ScheduledJob.lesson_starts_at == old_start)
            .values(run_at=datetime.now(UTC))
        )
    assert await handlers.run_due_jobs() == 1  # задача закрыта, но напоминание не отправлено
    assert len(await outbox("schedule.lesson.reminder")) == 1


async def test_calendar_range_is_limited(client, teacher):
    resp = await client.get("/lessons", params={"from": iso(at(0)), "to": iso(at(100))}, headers=bearer(teacher))
    assert resp.status_code == 422


async def test_internal_lessons_for_journal(client, teacher, fake_classroom):
    from testmatica_common.internal import INTERNAL_HEADER

    from app.config import settings

    h = {INTERNAL_HEADER: settings.internal_token}
    s1 = uuid4()
    gid = fake_classroom.group(teacher, [s1])
    await create(client, teacher, kind="group", group_id=str(gid), starts_at=iso(at(-3, 9)), duration_min=45,
                 repeat={"interval_weeks": 1, "count": 2}, timezone="UTC")
    params = {"teacher_id": str(teacher), "group_id": str(gid), **window(-5, 30)}
    lessons = (await client.get("/internal/lessons", params=params, headers=h)).json()
    assert len(lessons) == 2 and lessons[0]["participant_ids"] == [str(s1)]

    one = await client.get(f"/internal/lessons/{lessons[0]['id']}", params={"teacher_id": str(teacher)}, headers=h)
    assert one.json()["group_id"] == str(gid)
    other = await client.get(f"/internal/lessons/{lessons[0]['id']}", params={"teacher_id": str(uuid4())}, headers=h)
    assert other.status_code == 404
    assert (await client.get("/internal/lessons", params=params)).status_code == 403
    room = (await client.get(f"/internal/lessons/{lessons[0]['id']}/room", headers=h)).json()
    assert room["teacher_id"] == str(teacher) and room["group_title"] and room["participant_ids"] == [str(s1)]


async def test_lesson_exam_items(client, teacher, fake_classroom):
    """К занятию, кроме темы, привязываются задания ЕГЭ/ОГЭ; их видит и ученик."""
    item1, item2 = str(uuid4()), str(uuid4())
    student, lesson = await individual(client, teacher, fake_classroom, topic="Логика", exam_item_ids=[item1, item1, item2])
    assert lesson["exam_item_ids"] == [item1, item2]
    upd = await client.patch(f"/lessons/{lesson['id']}", json={"exam_item_ids": [item2]}, headers=bearer(teacher))
    assert upd.status_code == 200, upd.text
    theirs = (await client.get(f"/lessons/{lesson['id']}", headers=student_bearer(student))).json()
    assert theirs["exam_item_ids"] == [item2] and theirs["topic"] == "Логика"



async def test_paid_from_group_or_student_and_override(client, teacher, fake_classroom):
    """Режимов нет: платность берётся от группы или ученика, у отдельного занятия её можно поменять."""
    pupil = uuid4()
    paid_group = fake_classroom.group(teacher, [pupil], title="ЕГЭ", paid=True)
    free_group = fake_classroom.group(teacher, [pupil], title="7А")
    g1 = (await create(client, teacher, kind="group", group_id=str(paid_group), starts_at=iso(at(2, 10)), duration_min=45)).json()
    g2 = (await create(client, teacher, kind="group", group_id=str(free_group), starts_at=iso(at(2, 12)), duration_min=45)).json()
    assert g1["lessons"][0]["paid"] is True and g2["lessons"][0]["paid"] is False

    # Тот же ученик школьного класса — индивидуально и платно.
    fake_classroom.link(teacher, pupil, paid=True)
    ind = (await create(client, teacher, kind="individual", student_id=str(pupil), starts_at=iso(at(3, 10)), duration_min=60)).json()
    assert ind["lessons"][0]["paid"] is True
    trial = (await create(client, teacher, kind="individual", student_id=str(pupil), starts_at=iso(at(4, 10)), duration_min=60,
                          paid=False)).json()
    assert trial["lessons"][0]["paid"] is False  # пробное — бесплатно
    upd = await client.patch(f"/lessons/{ind['lessons'][0]['id']}", json={"paid": False}, headers=bearer(teacher))
    assert upd.json()["paid"] is False
    assert (await outbox("schedule.lesson.created"))[0]["data"]["paid"] is True
