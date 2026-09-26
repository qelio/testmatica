import os
import subprocess

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["RUN_BACKGROUND"] = "false"

from uuid import UUID, uuid4  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from testmatica_common.testing import TestTokens  # noqa: E402

from app import people  # noqa: E402
from app.config import settings  # noqa: E402
from app.deps import auth, classroom, db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

tokens = TestTokens()
auth.verifier = tokens.verifier(settings.jwt_issuer, settings.jwt_audience)


class FakeClassroom:
    """Имитация внутреннего API classroom."""

    def __init__(self) -> None:
        self.groups: dict[str, dict] = {}
        self.links: set[tuple[str, str]] = set()
        self.paid: dict[tuple[str, str], bool] = {}

    def group(self, teacher: UUID, members: list[UUID], title="7А", paid=False, archived=False) -> UUID:
        gid = uuid4()
        self.groups[str(gid)] = {
            "id": str(gid), "teacher_id": str(teacher), "title": title, "subject": "Алгебра", "paid": paid,
            "kind": "class", "archived": archived, "member_ids": [str(m) for m in members],
        }
        return gid

    def link(self, teacher: UUID, student: UUID, paid: bool = False) -> None:
        self.links.add((str(teacher), str(student)))
        self.paid[(str(teacher), str(student))] = paid

    def handle(self, request: httpx.Request) -> httpx.Response:
        path, params = request.url.path, request.url.params
        if path.startswith("/internal/groups/"):
            group = self.groups.get(path.rsplit("/", 1)[1])
            if group is None or group["teacher_id"] != params["teacher_id"]:
                return httpx.Response(404, json={"error": {"code": "group_not_found", "message": "Группа не найдена"}})
            return httpx.Response(200, json=group)
        if path == "/internal/links":
            key = (params["teacher_id"], params["student_id"])
            if key not in self.links:
                return httpx.Response(404, json={"error": {"code": "student_not_found", "message": "Не привязан"}})
            return httpx.Response(200, json={"teacher_id": key[0], "student_id": key[1], "active": True,
                                             "paid": self.paid.get(key, False)})
        return httpx.Response(500)


@pytest.fixture
def fake_classroom() -> FakeClassroom:
    fake = FakeClassroom()
    classroom.transport = httpx.MockTransport(fake.handle)
    return fake


def bearer(user_id: UUID, roles=("teacher",)) -> dict:
    token = tokens.issue(user_id, list(roles), settings.jwt_issuer, settings.jwt_audience)
    return {"Authorization": f"Bearer {token}"}


def student_bearer(user_id: UUID) -> dict:
    return bearer(user_id, ("student",))


@pytest.fixture(scope="session", autouse=True)
async def schema():
    # Настоящие миграции: проверяем и расширение btree_gist, и ограничение пересечений.
    async with db.engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=os.environ, capture_output=True)
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


@pytest.fixture
async def teacher() -> UUID:
    tid = uuid4()
    async with db.sessionmaker() as s, s.begin():
        await people.upsert(s, {"user_id": str(tid), "full_name": "Мария Ивановна", "roles": ["teacher"]})
    return tid


async def add_person(user_id: UUID, name: str) -> None:
    async with db.sessionmaker() as s, s.begin():
        await people.upsert(s, {"user_id": str(user_id), "full_name": name, "roles": ["student"]})


async def outbox(routing_key: str) -> list[dict]:
    async with db.engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT payload FROM outbox WHERE routing_key = :k ORDER BY created_at"), {"k": routing_key}
        )
        return [r[0] for r in rows]


SUBJECT_NAMES = ["Математика", "Алгебра", "Геометрия", "Физика", "Информатика"]


@pytest.fixture(autouse=True)
def fake_subjects():
    """Справочник предметов content (ведут модераторы)."""
    from app.deps import content, subjects

    content.transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=[{"id": str(i), "name": n} for i, n in enumerate(SUBJECT_NAMES)])
    )
    subjects.reset()

