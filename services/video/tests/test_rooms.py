from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update

from app import rooms
from app.deps import db
from app.models import Connection, Recording, Room

from .conftest import bearer, outbox, webhook

T = ("teacher",)


async def test_join_access_window_and_capacity(client, lk, lessons):
    teacher, pupil, stranger = uuid4(), uuid4(), uuid4()
    lesson = lessons.lesson(teacher, [pupil], minutes_from_now=10)
    joined = await client.post(f"/rooms/{lesson}/join", headers=bearer(pupil))
    assert joined.status_code == 200, joined.text
    body = joined.json()
    assert body["url"] == "ws://lk.test" and body["token"] == f"token-{pupil}"
    assert body["room"]["is_teacher"] is False and body["room"]["max_participants"] == 16 and body["room"]["status"] == "waiting"
    assert lk.rooms == {f"lesson-{lesson}": 17}  # 16 + невидимый участник записи
    assert lk.tokens[-1] == {"room": f"lesson-{lesson}", "identity": str(pupil), "name": "Участник", "teacher": False, "screen_share": False}

    assert (await client.post(f"/rooms/{lesson}/join", headers=bearer(stranger))).status_code == 404
    early = lessons.lesson(teacher, [pupil], minutes_from_now=25)
    assert (await client.post(f"/rooms/{early}/join", headers=bearer(pupil))).json()["error"]["code"] == "too_early"
    assert (await client.post(f"/rooms/{early}/join", headers=bearer(teacher, T))).status_code == 200  # педагогу — за 30 минут
    over = lessons.lesson(teacher, [pupil], minutes_from_now=-120)
    assert (await client.post(f"/rooms/{over}/join", headers=bearer(pupil))).json()["error"]["code"] == "lesson_over"
    cancelled = lessons.lesson(teacher, [pupil], status="cancelled")
    assert (await client.post(f"/rooms/{cancelled}/join", headers=bearer(pupil))).json()["error"]["code"] == "lesson_cancelled"
    single = lessons.lesson(teacher, [pupil], kind="individual")
    await client.post(f"/rooms/{single}/join", headers=bearer(pupil))
    assert lk.rooms[f"lesson-{single}"] == 3


async def test_screen_share_permission(client, lk, lessons):
    teacher, pupil = uuid4(), uuid4()
    lesson = lessons.lesson(teacher, [pupil])
    assert (await client.post(f"/rooms/{lesson}/screen-share", json={"student_id": str(pupil), "allowed": True},
                              headers=bearer(pupil))).status_code == 403
    room = (await client.post(f"/rooms/{lesson}/screen-share", json={"student_id": str(pupil), "allowed": True},
                              headers=bearer(teacher, T))).json()
    assert room["screen_share"] == [str(pupil)] and lk.permissions == [(f"lesson-{lesson}", str(pupil), True)]
    await client.post(f"/rooms/{lesson}/join", headers=bearer(pupil))
    assert lk.tokens[-1]["screen_share"] is True  # разрешение — и в токене при следующем входе
    await client.post(f"/rooms/{lesson}/screen-share", json={"student_id": str(pupil), "allowed": False}, headers=bearer(teacher, T))
    await client.post(f"/rooms/{lesson}/join", headers=bearer(pupil))
    assert lk.tokens[-1]["screen_share"] is False


async def test_connections_log_and_time_limit(client, lk, lessons):
    teacher, pupil = uuid4(), uuid4()
    lesson = lessons.lesson(teacher, [pupil])
    await client.post(f"/rooms/{lesson}/join", headers=bearer(teacher, T))
    name = f"lesson-{lesson}"
    await webhook("participant_joined", name, identity=str(teacher), participant_sid="PA_1")
    await webhook("participant_joined", name, identity=str(pupil), participant_sid="PA_2")
    await webhook("participant_joined", name, identity="EG_recorder", participant_sid="PA_3")  # служебный — без записи в лог
    await webhook("participant_left", name, identity=str(pupil), participant_sid="PA_2")
    async with db.sessionmaker() as s:
        conns = {c.user_id: c for c in (await s.execute(select(Connection))).scalars()}
    assert set(conns) == {teacher, pupil} and conns[pupil].left_at is not None and conns[teacher].left_at is None
    room = (await client.get(f"/rooms/{lesson}", headers=bearer(pupil))).json()
    assert room["status"] == "active" and room["limit_ends_at"] is not None
    assert (await outbox("video.room.started"))[0]["data"]["lesson_id"] == str(lesson)

    # 40 минут истекли — комната закрывается для всех, повторный вход запрещён.
    async with db.sessionmaker() as s, s.begin():
        await s.execute(update(Room).values(started_at=datetime.now(UTC) - timedelta(minutes=41)))
    await rooms.enforce_limits()
    assert lk.deleted == [name]
    again = await client.post(f"/rooms/{lesson}/join", headers=bearer(teacher, T))
    assert again.json()["error"]["code"] == "time_limit"
    assert (await outbox("video.room.ended"))[0]["data"]["reason"] == "time_limit"
    async with db.sessionmaker() as s:
        assert all(c.left_at for c in (await s.execute(select(Connection))).scalars())


async def test_teacher_ends_and_reopens(client, lk, lessons):
    teacher, pupil = uuid4(), uuid4()
    lesson = lessons.lesson(teacher, [pupil])
    await client.post(f"/rooms/{lesson}/join", headers=bearer(teacher, T))
    await webhook("participant_joined", f"lesson-{lesson}", identity=str(teacher), participant_sid="PA_1")
    assert (await client.post(f"/rooms/{lesson}/end", headers=bearer(pupil))).status_code == 403
    ended = (await client.post(f"/rooms/{lesson}/end", headers=bearer(teacher, T))).json()
    assert ended["status"] == "ended" and ended["end_reason"] == "teacher"
    assert (await client.post(f"/rooms/{lesson}/join", headers=bearer(pupil))).json()["error"]["code"] == "room_closed"
    assert (await client.post(f"/rooms/{lesson}/join", headers=bearer(teacher, T))).status_code == 200
    assert (await client.post(f"/rooms/{lesson}/join", headers=bearer(pupil))).status_code == 200


async def test_recording_lifecycle_and_retention(client, lk, lessons, s3):
    teacher, pupil, other = uuid4(), uuid4(), uuid4()
    lesson = lessons.lesson(teacher, [pupil])
    name = f"lesson-{lesson}"
    await client.post(f"/rooms/{lesson}/join", headers=bearer(teacher, T))
    early = await client.post(f"/rooms/{lesson}/recording", params={"action": "start"}, headers=bearer(teacher, T))
    assert early.json()["error"]["code"] == "room_not_active"
    await webhook("participant_joined", name, identity=str(teacher), participant_sid="PA_1")

    # Запись включилась сама, как только педагог вошёл (решение №40); второй раз не включить.
    assert (await client.get(f"/rooms/{lesson}", headers=bearer(teacher, T))).json()["recording"] == "starting"
    assert (await client.post(f"/rooms/{lesson}/recording", params={"action": "start"}, headers=bearer(teacher, T))).status_code == 409
    await webhook("participant_joined", name, identity=str(pupil), participant_sid="PA_2")
    assert len(lk.egress) == 1  # вход ученика не запускает вторую запись
    [(egress_id, path)] = lk.egress.items()
    # Пока egress запускает Chrome, остановить нельзя — иначе файла не будет.
    too_soon = await client.post(f"/rooms/{lesson}/recording", params={"action": "stop"}, headers=bearer(teacher, T))
    assert too_soon.json()["error"]["code"] == "recording_starting"
    await webhook("egress_updated", name, egress_id=egress_id, egress_status="EGRESS_ACTIVE")
    assert (await client.get(f"/rooms/{lesson}", headers=bearer(pupil))).json()["recording"] == "active"
    assert path.startswith(f"lessons/{lesson}/") and path.endswith(".mp4")
    listed = (await client.get("/recordings", headers=bearer(pupil))).json()
    assert [r["status"] for r in listed] == ["recording"] and listed[0]["url"] is None

    stopping = (await client.post(f"/rooms/{lesson}/recording", params={"action": "stop"}, headers=bearer(teacher, T))).json()
    assert lk.stopped == [egress_id] and stopping["recording"] == "stopping"
    await webhook("egress_ended", name, egress_id=egress_id, egress_status="EGRESS_COMPLETE", file_size=1_000_000, file_duration_s=600)
    # Педагог выключил запись сам — переподключение её не включает.
    await webhook("participant_joined", name, identity=str(pupil), participant_sid="PA_3")
    assert len(lk.egress) == 1
    assert (await client.get(f"/rooms/{lesson}", headers=bearer(pupil))).json()["recording"] is None
    rec = (await client.get("/recordings", params={"lesson_id": str(lesson)}, headers=bearer(pupil))).json()[0]
    assert rec["status"] == "ready" and rec["duration_s"] == 600 and rec["url"].endswith("download=0") and rec["download_url"].endswith("download=1")
    assert rec["can_delete"] is False and rec["expires_at"] is not None
    assert (await client.get("/recordings", headers=bearer(other))).json() == []  # посторонний не видит
    ready = (await outbox("video.recording.ready"))[0]["data"]
    assert ready["viewer_ids"] == [str(pupil)]

    # Бесплатный тариф: у педагога не больше 3 записей — четвёртая вытесняет самую старую.
    async with db.sessionmaker() as s, s.begin():
        room_id = await s.scalar(select(Room.id))
        for i in range(3):
            s.add(Recording(room_id=room_id, lesson_id=lesson, teacher_id=teacher, title=f"R{i}", viewer_ids=[pupil],
                            egress_id=f"EG_old{i}", key=f"k{i}", status="ready",
                            started_at=datetime.now(UTC) - timedelta(days=i + 1)))
    async with db.sessionmaker() as s, s.begin():
        await rooms.apply_retention(s, teacher)
    assert s3 == ["k2"]  # самая старая
    assert len((await client.get("/recordings", headers=bearer(teacher, T))).json()) == 3

    # Срок хранения истёк — файл удаляется.
    async with db.sessionmaker() as s, s.begin():
        await s.execute(update(Recording).where(Recording.egress_id == "EG_old0").values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    await rooms.enforce_limits()
    assert s3 == ["k2", "k0"]
    assert (await client.delete(f"/recordings/{rec['id']}", headers=bearer(pupil))).status_code == 404
    assert (await client.delete(f"/recordings/{rec['id']}", headers=bearer(teacher, T))).status_code == 204


async def test_recording_failure(client, lk, lessons):
    teacher = uuid4()
    lesson = lessons.lesson(teacher, [uuid4()])
    await client.post(f"/rooms/{lesson}/join", headers=bearer(teacher, T))
    lk.fail_recording = True
    # Автозапись не удалась — вход в комнату это не ломает, педагог может включить запись сам.
    await webhook("participant_joined", f"lesson-{lesson}", identity=str(teacher), participant_sid="PA_1")
    assert lk.egress == {}
    resp = await client.post(f"/rooms/{lesson}/recording", params={"action": "start"}, headers=bearer(teacher, T))
    assert resp.json()["error"]["code"] == "recording_failed"
    lk.fail_recording = False
    await client.post(f"/rooms/{lesson}/recording", params={"action": "start"}, headers=bearer(teacher, T))
    [egress_id] = lk.egress
    await webhook("egress_ended", f"lesson-{lesson}", egress_id=egress_id, egress_status="EGRESS_ABORTED", egress_error="Stop called before pipeline could start")
    # Педагог видит, что запись не сохранилась, и может убрать её из списка; ученики — нет.
    [failed] = (await client.get("/recordings", headers=bearer(teacher, T))).json()
    assert failed["status"] == "failed" and failed["error"] == "Stop called before pipeline could start"
    assert (await client.delete(f"/recordings/{failed['id']}", headers=bearer(teacher, T))).status_code == 204
    assert (await client.get("/recordings", headers=bearer(teacher, T))).json() == []
    async with db.sessionmaker() as s:
        assert (await s.scalar(select(Recording.status))) == "expired"


async def test_webhook_signature_required(client):
    resp = await client.post("/internal/webhooks/livekit", content="{}", headers={"Authorization": "bad"})
    assert resp.status_code == 401



async def test_paid_lessons_have_no_time_limit(client, lessons):
    teacher = uuid4()
    lesson = lessons.lesson(teacher, [uuid4()], paid=True)
    await client.post(f"/rooms/{lesson}/join", headers=bearer(teacher, T))
    await webhook("participant_joined", f"lesson-{lesson}", identity=str(teacher), participant_sid="PA_1")
    room = (await client.get(f"/rooms/{lesson}", headers=bearer(teacher, T))).json()
    assert room["status"] == "active" and room["limit_ends_at"] is None


async def test_basic_plan_removes_limits(client, lessons, s3):
    from .conftest import BASIC_TEACHERS

    teacher, pupil = uuid4(), uuid4()
    # Педагог подключил «Базовый» во время бесплатного занятия — таймер снимается, звонок не обрывается.
    lesson = lessons.lesson(teacher, [pupil])
    await client.post(f"/rooms/{lesson}/join", headers=bearer(teacher, T))
    await webhook("participant_joined", f"lesson-{lesson}", identity=str(teacher), participant_sid="PA_1")
    assert (await client.get(f"/rooms/{lesson}", headers=bearer(teacher, T))).json()["limit_ends_at"] is not None
    BASIC_TEACHERS.add(str(teacher))
    async with db.sessionmaker() as s, s.begin():
        await s.execute(update(Room).values(started_at=datetime.now(UTC) - timedelta(minutes=45)))
    await rooms.enforce_limits()
    room = (await client.get(f"/rooms/{lesson}", headers=bearer(teacher, T))).json()
    assert room["status"] == "active" and room["limit_ends_at"] is None

    # Новые комнаты — сразу без лимита; записи не вытесняются.
    other = lessons.lesson(teacher, [pupil])
    await client.post(f"/rooms/{other}/join", headers=bearer(teacher, T))
    await webhook("participant_joined", f"lesson-{other}", identity=str(teacher), participant_sid="PA_2")
    assert (await client.get(f"/rooms/{other}", headers=bearer(teacher, T))).json()["limit_ends_at"] is None
    async with db.sessionmaker() as s, s.begin():
        room_id = await s.scalar(select(Room.id).limit(1))
        for i in range(5):
            s.add(Recording(room_id=room_id, lesson_id=lesson, teacher_id=teacher, title=f"R{i}", viewer_ids=[pupil],
                            egress_id=f"EG_b{i}", key=f"b{i}", status="ready", started_at=datetime.now(UTC) - timedelta(days=i)))
    async with db.sessionmaker() as s, s.begin():
        await rooms.apply_retention(s, teacher)
    assert s3 == []
