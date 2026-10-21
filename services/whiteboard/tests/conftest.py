import os

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://redis:6379/13")
os.environ["RUN_BACKGROUND"] = "false"

from datetime import UTC, datetime  # noqa: E402
from uuid import UUID, uuid4  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from testmatica_common.testing import TestTokens, make_envelope  # noqa: E402

from app import people  # noqa: E402
from app.config import settings  # noqa: E402
from app.deps import auth, classroom, db, redis, schedule, verifier  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

tokens = TestTokens()
auth.verifier = tokens.verifier(settings.jwt_issuer, settings.jwt_audience)
verifier._keys = auth.verifier._keys  # WebSocket проверяет токен тем же ключом
verifier._fetched_at = float("inf")


def token(user_id: UUID, roles=("teacher",)) -> str:
    return tokens.issue(user_id, list(roles), settings.jwt_issuer, settings.jwt_audience)


def bearer(user_id: UUID, roles=("teacher",)) -> dict:
    return {"Authorization": f"Bearer {token(user_id, roles)}"}


def student(user_id: UUID) -> dict:
    return bearer(user_id, ("student",))


class World:
    """Занятия (schedule) и классы, привязки (classroom)."""

    def __init__(self) -> None:
        self.lessons: dict[str, dict] = {}
        self.groups: dict[str, dict] = {}
        self.links: set[tuple[str, str]] = set()

    def lesson(self, teacher: UUID, participants: list[UUID], group_id: UUID | None = None, subject="Алгебра") -> UUID:
        lid = uuid4()
        self.lessons[str(lid)] = {
            "id": str(lid), "teacher_id": str(teacher), "group_id": str(group_id) if group_id else None,
            "student_id": None if group_id else str(participants[0]), "subject": subject, "topic": "Дроби",
            "starts_at": datetime(2026, 10, 21, 9, 0, tzinfo=UTC).isoformat(), "status": "scheduled",
            "participant_ids": [str(p) for p in participants], "group_title": "7А" if group_id else None,
        }
        return lid

    def group(self, teacher: UUID, members: list[UUID]) -> UUID:
        gid = uuid4()
        self.groups[str(gid)] = {"id": str(gid), "teacher_id": str(teacher), "title": "7А", "member_ids": [str(m) for m in members]}
        return gid

    def schedule_handler(self, request: httpx.Request) -> httpx.Response:
        lesson = self.lessons.get(request.url.path.rsplit("/", 1)[-1])
        if lesson is None or lesson["teacher_id"] != request.url.params["teacher_id"]:
            return httpx.Response(404, json={"error": {"code": "lesson_not_found", "message": "Занятие не найдено"}})
        return httpx.Response(200, json=lesson)

    def classroom_handler(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if request.url.path.startswith("/internal/groups/"):
            group = self.groups.get(request.url.path.rsplit("/", 1)[-1])
            if group is None or group["teacher_id"] != params["teacher_id"]:
                return httpx.Response(404, json={"error": {"code": "group_not_found", "message": "Группа не найдена"}})
            return httpx.Response(200, json=group)
        if (params["teacher_id"], params["student_id"]) not in self.links:
            return httpx.Response(404, json={"error": {"code": "student_not_found", "message": "Ученик не привязан"}})
        return httpx.Response(200, json={"active": True})


@pytest.fixture
def world() -> World:
    w = World()
    schedule.transport = httpx.MockTransport(w.schedule_handler)
    classroom.transport = httpx.MockTransport(w.classroom_handler)
    return w


@pytest.fixture(scope="session", autouse=True)
async def schema():
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await db.dispose()
    await redis.aclose()


@pytest.fixture(autouse=True)
async def clean():
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with db.engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def person(name: str) -> UUID:
    uid = uuid4()
    async with db.sessionmaker() as s, s.begin():
        await people.on_identity_event(make_envelope("identity.user.registered", {"user_id": str(uid), "full_name": name, "login": None}), s)
    return uid
