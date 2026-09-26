import os

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["RUN_BACKGROUND"] = "false"

from datetime import UTC, datetime, timedelta  # noqa: E402
from uuid import UUID, uuid4  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from testmatica_common.testing import TestTokens  # noqa: E402

from app import storage  # noqa: E402
from app.config import settings  # noqa: E402
from app.deps import assessment, auth, billing, db, livekit, plans, schedule  # noqa: E402
from app.lk import LiveKitError, WebhookEvent  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

tokens = TestTokens()
auth.verifier = tokens.verifier(settings.jwt_issuer, settings.jwt_audience)


def bearer(user_id: UUID, roles=("student",)) -> dict:
    return {"Authorization": f"Bearer {tokens.issue(user_id, list(roles), settings.jwt_issuer, settings.jwt_audience)}"}


class FakeLiveKit:
    """Вместо LiveKit: запоминает вызовы, вебхуки подаются напрямую событиями."""

    def __init__(self) -> None:
        self.rooms: dict[str, int] = {}
        self.deleted: list[str] = []
        self.tokens: list[dict] = []
        self.permissions: list[tuple[str, str, bool]] = []
        self.egress: dict[str, str] = {}  # egress_id → путь файла
        self.stopped: list[str] = []
        self.fail_recording = False
        self.public_url = "ws://lk.test"

    def token(self, room, identity, name, teacher, screen_share, ttl):
        self.tokens.append({"room": room, "identity": identity, "name": name, "teacher": teacher, "screen_share": screen_share})
        return f"token-{identity}"

    def proctor_token(self, room, identity, name, teacher, metadata, ttl):
        self.tokens.append({"room": room, "identity": identity, "name": name, "teacher": teacher, "metadata": metadata})
        return f"proctor-token-{identity}"

    async def start_track_recording(self, room, track_sid, filepath):
        egress_id = f"EG_T{len(self.egress) + 1}"
        self.egress[egress_id] = filepath
        return egress_id

    async def create_room(self, name, max_participants):
        self.rooms[name] = max_participants

    async def delete_room(self, name):
        self.deleted.append(name)

    async def set_screen_share(self, room, identity, allowed):
        self.permissions.append((room, identity, allowed))

    async def start_recording(self, room, filepath):
        if self.fail_recording:
            raise LiveKitError("no egress available")
        egress_id = f"EG_{len(self.egress) + 1}"
        self.egress[egress_id] = filepath
        return egress_id

    async def stop_recording(self, egress_id):
        self.stopped.append(egress_id)

    def parse_webhook(self, body, auth_header):
        raise ValueError("bad signature")


class FakeSchedule:
    def __init__(self) -> None:
        self.lessons: dict[str, dict] = {}

    def lesson(self, teacher: UUID, students: list[UUID], minutes_from_now: int = 0, kind="group", status="scheduled",
               paid: bool = False) -> UUID:
        lid = uuid4()
        start = datetime.now(UTC) + timedelta(minutes=minutes_from_now)
        self.lessons[str(lid)] = {
            "id": str(lid), "teacher_id": str(teacher), "kind": kind, "paid": paid,
            "group_id": str(uuid4()) if kind == "group" else None, "student_id": str(students[0]) if kind == "individual" else None,
            "subject": "Математика", "topic": None, "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(minutes=60)).isoformat(), "status": status,
            "participant_ids": [str(s) for s in students], "group_title": "9Б" if kind == "group" else None, "video_url": None,
        }
        return lid

    def handler(self, request: httpx.Request) -> httpx.Response:
        lesson = self.lessons.get(request.url.path.split("/")[3])
        if lesson is None:
            return httpx.Response(404, json={"error": {"code": "lesson_not_found", "message": "Занятие не найдено"}})
        return httpx.Response(200, json=lesson)


@pytest.fixture(autouse=True)
def lk(monkeypatch) -> FakeLiveKit:
    fake = FakeLiveKit()
    for name in ("token", "proctor_token", "create_room", "delete_room", "set_screen_share", "start_recording", "stop_recording",
                 "start_track_recording"):
        monkeypatch.setattr(livekit, name, getattr(fake, name))
    monkeypatch.setattr(livekit, "public_url", fake.public_url)
    return fake


@pytest.fixture(autouse=True)
def s3(monkeypatch) -> list[str]:
    deleted: list[str] = []

    async def delete(key):
        deleted.append(key)

    async def url(key, filename, download):
        return f"http://s3.test/{key}?download={int(download)}"

    monkeypatch.setattr(storage, "delete", delete)
    monkeypatch.setattr(storage, "url", url)
    return deleted


BASIC_TEACHERS: set[str] = set()


@pytest.fixture(autouse=True)
def fake_billing():
    """Тарифы: по умолчанию бесплатный, «Базовый» — у педагогов из BASIC_TEACHERS."""
    import json

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/internal/settings":
            return httpx.Response(200, json={})  # настройки по умолчанию
        ids = json.loads(request.content)["user_ids"]
        return httpx.Response(200, json={u: "basic" if u in BASIC_TEACHERS else "free" for u in ids})

    billing.transport = httpx.MockTransport(handle)
    plans.reset()
    BASIC_TEACHERS.clear()


class FakeAssessment:
    """Доступ к прокторингу: assignment_id → {teacher_id, students: {id: attempt_id|None}}."""

    def __init__(self) -> None:
        self.assignments: dict[str, dict] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        a = self.assignments.get(request.url.path.split("/")[3])
        user = request.url.params["user_id"]
        not_found = httpx.Response(404, json={"error": {"code": "assignment_not_found", "message": "Не найден"}})
        if a is None:
            return not_found
        base = {"assignment_id": request.url.path.split("/")[3], "teacher_id": a["teacher_id"], "title": "Контрольная", "closed": False}
        if user == a["teacher_id"]:
            students = [{"id": sid, "full_name": "Ученик", "attempt_id": att} for sid, att in a["students"].items()]
            return httpx.Response(200, json=base | {"role": "teacher", "students": students, "attempt_id": None})
        if user in a["students"]:
            return httpx.Response(200, json=base | {"role": "student", "attempt_id": a["students"][user], "students": []})
        return not_found


@pytest.fixture(autouse=True)
def proctored() -> FakeAssessment:
    fake = FakeAssessment()
    assessment.transport = httpx.MockTransport(fake.handler)
    return fake


@pytest.fixture(autouse=True)
def lessons() -> FakeSchedule:
    fake = FakeSchedule()
    schedule.transport = httpx.MockTransport(fake.handler)
    return fake


@pytest.fixture(scope="session", autouse=True)
async def schema():
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await db.dispose()


@pytest.fixture(autouse=True)
async def clean():
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with db.engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def webhook(event: str, room: str | None = None, **fields) -> None:
    from app import rooms

    async with db.sessionmaker() as s, s.begin():
        await rooms.on_webhook(s, WebhookEvent(event=event, room=room, **fields))


async def outbox(key: str) -> list[dict]:
    async with db.engine.connect() as conn:
        rows = await conn.execute(text("SELECT payload FROM outbox WHERE routing_key = :k ORDER BY created_at"), {"k": key})
        return [r[0] for r in rows]
