import json
import os
import subprocess

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["RUN_BACKGROUND"] = "false"

from datetime import UTC, datetime, timedelta  # noqa: E402
from uuid import UUID, uuid4  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from testmatica_common.testing import TestTokens  # noqa: E402

from app import people  # noqa: E402
from app.config import settings  # noqa: E402
from app.deps import auth, billing, classroom, db, plans, schedule  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

tokens = TestTokens()
auth.verifier = tokens.verifier(settings.jwt_issuer, settings.jwt_audience)


def not_found(code: str) -> httpx.Response:
    return httpx.Response(404, json={"error": {"code": code, "message": "Не найдено"}})


class World:
    """Имитация schedule и classroom: группы, привязки и занятия одного или нескольких педагогов."""

    def __init__(self) -> None:
        self.groups: dict[str, dict] = {}
        self.links: set[tuple[str, str]] = set()
        self.lessons: dict[str, dict] = {}
        self.basic: set[str] = set()  # педагоги на тарифе «Базовый»
        self.shares: set[tuple[str, str]] = set()  # (группа, коллега) — классом поделились (решение №57)
        self.share_perms: dict[tuple[str, str], list[str]] = {}  # права коллеги (решение №61)

    def group(self, teacher: UUID, members: list[UUID], title="7А") -> UUID:
        gid = uuid4()
        self.groups[str(gid)] = {
            "id": str(gid), "teacher_id": str(teacher), "title": title, "subject": "Алгебра", "paid": False,
            "kind": "class", "archived": False, "member_ids": [str(m) for m in members],
        }
        return gid

    def lesson(
        self, teacher: UUID, participants: list[UUID], days: int, group_id: UUID | None = None,
        student_id: UUID | None = None, subject="Алгебра", status="scheduled",
    ) -> UUID:
        lid = uuid4()
        start = datetime.now(UTC).replace(microsecond=0) + timedelta(days=days)
        self.lessons[str(lid)] = {
            "id": str(lid), "teacher_id": str(teacher), "kind": "group" if group_id else "individual", "paid": False,
            "group_id": str(group_id) if group_id else None, "student_id": str(student_id) if student_id else None,
            "subject": subject, "topic": None, "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(minutes=45)).isoformat(), "status": status,
            "participant_ids": [str(p) for p in participants],
        }
        return lid

    def schedule_handler(self, request: httpx.Request) -> httpx.Response:
        path, params = request.url.path, request.url.params
        if path == "/internal/lessons":
            start, end = datetime.fromisoformat(params["from"]), datetime.fromisoformat(params["to"])
            key, value = ("group_id", params["group_id"]) if "group_id" in params else ("student_id", params["student_id"])
            found = [
                lesson for lesson in self.lessons.values()
                if (lesson["teacher_id"] == params["teacher_id"] or params.get("all_teachers") == "true") and lesson[key] == value
                and start <= datetime.fromisoformat(lesson["starts_at"]) < end
            ]
            return httpx.Response(200, json=sorted(found, key=lambda lesson: lesson["starts_at"]))
        lesson = self.lessons.get(path.rsplit("/", 1)[1])
        if lesson is None or lesson["teacher_id"] != params["teacher_id"]:
            return not_found("lesson_not_found")
        return httpx.Response(200, json=lesson)

    def classroom_handler(self, request: httpx.Request) -> httpx.Response:
        path, params = request.url.path, request.url.params
        if path.startswith("/internal/teachers/"):
            teacher = path.split("/")[3]
            return httpx.Response(200, json=[g for g in self.groups.values() if g["teacher_id"] == teacher])
        if path.startswith("/internal/groups/"):
            group = self.groups.get(path.rsplit("/", 1)[1])
            if group is None or (group["teacher_id"] != params["teacher_id"] and (group["id"], params["teacher_id"]) not in self.shares):
                return not_found("group_not_found")
            key = (group["id"], params["teacher_id"])
            perms = ["owner", "journal_all"] if group["teacher_id"] == params["teacher_id"] else self.share_perms.get(key, [])
            return httpx.Response(200, json=group | {"permissions": perms})
        key = (params["teacher_id"], params["student_id"])
        if key not in self.links:
            return not_found("student_not_found")
        return httpx.Response(200, json={"teacher_id": key[0], "student_id": key[1], "active": True})


@pytest.fixture
def world() -> World:
    w = World()
    schedule.transport = httpx.MockTransport(w.schedule_handler)
    classroom.transport = httpx.MockTransport(w.classroom_handler)
    billing.transport = httpx.MockTransport(
        lambda r: httpx.Response(200, json={u: "basic" if u in w.basic else "free" for u in json.loads(r.content)["user_ids"]})
    )
    plans.reset()
    return w


def bearer(user_id: UUID, roles=("teacher",)) -> dict:
    token = tokens.issue(user_id, list(roles), settings.jwt_issuer, settings.jwt_audience)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session", autouse=True)
async def schema():
    async with db.engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=os.environ, capture_output=True)
    yield
    await db.dispose()


@pytest.fixture(autouse=True)
async def clean():
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables if t.name != "grade_types")
    async with db.engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    yield
    # Типы по умолчанию из миграции оставляем, созданные тестами — удаляем.
    async with db.engine.begin() as conn:
        await conn.execute(text("DELETE FROM grade_types WHERE name LIKE 'Тест%'"))
        await conn.execute(text("UPDATE grade_types SET is_active = true"))


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def add_person(user_id: UUID, name: str, roles=("student",)) -> None:
    async with db.sessionmaker() as s, s.begin():
        await people.upsert(s, {"user_id": str(user_id), "full_name": name, "roles": list(roles)})


async def outbox(routing_key: str) -> list[dict]:
    async with db.engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT payload FROM outbox WHERE routing_key = :k ORDER BY created_at"), {"k": routing_key}
        )
        return [r[0] for r in rows]
