import os

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["RUN_BACKGROUND"] = "false"

import json  # noqa: E402
from uuid import UUID, uuid4  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from testmatica_common.testing import TestTokens  # noqa: E402

from app import people  # noqa: E402
from app.config import settings  # noqa: E402
from app.deps import auth, db, identity  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

tokens = TestTokens()
auth.verifier = tokens.verifier(settings.jwt_issuer, settings.jwt_audience)


class FakeIdentity:
    """Имитация внутреннего API identity."""

    def __init__(self) -> None:
        self.users: dict[str, dict] = {}  # логин/email -> PersonOut

    def add(self, identifier: str, full_name: str, roles=("student",), user_id: UUID | None = None) -> UUID:
        uid = user_id or uuid4()
        self.users[identifier] = {
            "id": str(uid), "full_name": full_name, "login": identifier, "roles": list(roles), "managed_by_teacher_id": None,
        }
        return uid

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/internal/users/lookup":
            user = self.users.get(request.url.params["identifier"].lower())
            if user is None:
                return httpx.Response(404, json={"error": {"code": "user_not_found", "message": "Не найден"}})
            return httpx.Response(200, json=user)
        if path == "/internal/managed-students" and request.method == "POST":
            body = json.loads(request.content)
            if body["full_name"] == "Занятый Логин":
                return httpx.Response(409, json={"error": {"code": "login_taken", "message": "Такой логин уже занят"}})
            login = body.get("login") or f"auto{len(self.users)}"
            uid = str(uuid4())
            user = {"id": uid, "full_name": body["full_name"], "login": login, "roles": ["student"],
                    "managed_by_teacher_id": body["teacher_id"]}
            self.users[login] = user
            return httpx.Response(201, json={"user": user, "login": login, "password": body.get("password") or "gen-pass-1"})
        if path.startswith("/internal/managed-students/") and request.method == "PATCH":
            body = json.loads(request.content)
            uid = path.rsplit("/", 1)[1]
            user = next(u for u in self.users.values() if u["id"] == uid)
            if body.get("full_name"):
                user["full_name"] = body["full_name"]
            return httpx.Response(
                200, json={"user": user, "login": user["login"], "password": "new-pass-2" if body.get("reset_password") else None}
            )
        return httpx.Response(500)


@pytest.fixture
def fake_identity() -> FakeIdentity:
    fake = FakeIdentity()
    identity.transport = httpx.MockTransport(fake.handle)
    return fake


def bearer(user_id: UUID, roles=("teacher",)) -> dict:
    token = tokens.issue(user_id, list(roles), settings.jwt_issuer, settings.jwt_audience)
    return {"Authorization": f"Bearer {token}"}


def student_bearer(user_id: UUID) -> dict:
    return bearer(user_id, ("student",))


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


@pytest.fixture
async def teacher() -> UUID:
    """Педагог, известный реплике people (как будто пришло событие из identity)."""
    tid = uuid4()
    async with db.sessionmaker() as s, s.begin():
        await people.upsert(s, tid, "Мария Ивановна", None, ["teacher"])
    return tid


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



BASIC_TEACHERS: set[str] = set()


@pytest.fixture(autouse=True)
def fake_billing():
    """Тарифы billing: по умолчанию бесплатный, «Базовый» — у педагогов из BASIC_TEACHERS."""
    from app.deps import billing, plans

    def handle(request: httpx.Request) -> httpx.Response:
        ids = json.loads(request.content)["user_ids"]
        return httpx.Response(200, json={u: "basic" if u in BASIC_TEACHERS else "free" for u in ids})

    billing.transport = httpx.MockTransport(handle)
    plans.reset()
    BASIC_TEACHERS.clear()
