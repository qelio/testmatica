from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import update

from app import rooms
from app.deps import db
from app.models import ProctorRecording

from .conftest import bearer, webhook

T = ("teacher",)


async def test_proctoring_join_and_screen_recording(client, lk, proctored, s3):
    teacher, pupil, idle, stranger = uuid4(), uuid4(), uuid4(), uuid4()
    assignment, attempt = uuid4(), uuid4()
    proctored.assignments[str(assignment)] = {"teacher_id": str(teacher), "students": {str(pupil): str(attempt), str(idle): None}}

    # Педагог смотрит, ученик с идущей попыткой показывает экран; без попытки и посторонним — нельзя.
    t = (await client.post(f"/proctoring/{assignment}/join", headers=bearer(teacher, T))).json()
    assert t["role"] == "teacher" and len(t["students"]) == 2 and lk.tokens[-1]["teacher"] is True
    s = (await client.post(f"/proctoring/{assignment}/join", headers=bearer(pupil))).json()
    assert s["role"] == "student" and s["token"] == f"proctor-token-{pupil}"
    assert lk.tokens[-1]["metadata"] == {"role": "student", "teacher_id": str(teacher), "title": "Контрольная", "attempt_id": str(attempt)}
    assert (await client.post(f"/proctoring/{assignment}/join", headers=bearer(idle))).json()["error"]["code"] == "no_attempt"
    assert (await client.post(f"/proctoring/{assignment}/join", headers=bearer(stranger))).status_code == 404
    assert lk.rooms[f"proctor-{assignment}"] == 17

    # Ученик включил показ экрана — дорожка пишется в отдельный файл; камера не пишется.
    room = f"proctor-{assignment}"
    # Как в настоящих вебхуках о дорожках: только идентификатор участника, без метаданных пропуска.
    await webhook("track_published", room, identity=str(pupil), track_sid="TR_cam", track_source="CAMERA")
    await webhook("track_published", room, identity=str(teacher), track_sid="TR_x", track_source="SCREEN_SHARE")  # не ученик
    await webhook("track_published", room, identity=str(pupil), track_sid="TR_screen", track_source="SCREEN_SHARE")
    [(egress_id, path)] = lk.egress.items()
    assert path.startswith(f"proctoring/{assignment}/{pupil}/") and path.endswith("TR_screen")
    await webhook("egress_ended", room, egress_id=egress_id, egress_status="EGRESS_COMPLETE", file_size=5000, file_duration_s=900,
                  file_name=f"{path}.webm")

    recs = (await client.get(f"/proctoring/{assignment}/recordings", headers=bearer(teacher, T))).json()
    assert len(recs) == 1 and recs[0]["status"] == "ready" and recs[0]["attempt_id"] == str(attempt) and recs[0]["url"]
    assert datetime.fromisoformat(recs[0]["expires_at"]) - datetime.now(UTC) > timedelta(days=13)
    assert (await client.get(f"/proctoring/{assignment}/recordings", headers=bearer(pupil))).status_code == 404

    # Через 14 дней файл удаляется.
    async with db.sessionmaker() as ses, ses.begin():
        await ses.execute(update(ProctorRecording).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    await rooms.enforce_limits()
    assert s3 == [f"{path}.webm"]
    assert (await client.get(f"/proctoring/{assignment}/recordings", headers=bearer(teacher, T))).json() == []


def test_egress_duration_sanity():
    from app.lk import _duration_s

    started = 1_790_455_815 * 10**9
    assert _duration_s(-started, started, started + 27 * 10**9) == 27  # мусор в duration — по началу и концу
    assert _duration_s(600 * 10**9, 0, 0) == 600
    assert _duration_s(-started, 0, 0) is None
