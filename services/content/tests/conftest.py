import os
import subprocess

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["RUN_BACKGROUND"] = "false"

import json  # noqa: E402
from uuid import UUID, uuid4  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from testmatica_common.testing import TestTokens, make_envelope  # noqa: E402

from app import handlers  # noqa: E402
from app.config import settings  # noqa: E402
from app.deps import assessment, auth, classroom, db, media  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

tokens = TestTokens()
auth.verifier = tokens.verifier(settings.jwt_issuer, settings.jwt_audience)


def bearer(user_id: UUID, roles=("teacher",)) -> dict:
    return {"Authorization": f"Bearer {tokens.issue(user_id, list(roles), settings.jwt_issuer, settings.jwt_audience)}"}


def student(user_id: UUID) -> dict:
    return bearer(user_id, ("student",))


class FakeServices:
    def __init__(self) -> None:
        self.files: dict[str, dict] = {}
        self.groups: dict[str, dict] = {}
        self.tasks: dict[str, dict] = {}

    def task(self, owner: UUID, title: str, type_: str = "choice", status: str = "private") -> str:
        tid = str(uuid4())
        self.tasks[tid] = {"id": tid, "title": title, "type": type_, "status": status, "owner_id": str(owner)}
        return tid

    def assessment(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        out = []
        for tid in body["task_ids"]:
            t = self.tasks.get(tid)
            if t:
                out.append(t | {"auto_checked": t["type"] != "long",
                                "usable": t["owner_id"] == body["user_id"] or t["status"] == "published"})
        return httpx.Response(200, json=out)

    def file(self, owner: UUID, filename: str, mime: str) -> str:
        fid = str(uuid4())
        self.files[fid] = {"id": fid, "owner": str(owner), "filename": filename, "mime": mime, "size": 100}
        return fid

    def media(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        out = lambda f, url=None: {"id": f["id"], "filename": f["filename"], "mime": f["mime"], "size": f["size"],  # noqa: E731
                                   "purpose": "material", "created_at": "2026-09-25T00:00:00Z", "url": url}
        if request.url.path.endswith("/claim"):
            f = self.files.get(body["file_ids"][0])
            if f is None or f["owner"] != body["owner_id"]:
                return httpx.Response(422, json={"error": {"code": "invalid_attachment", "message": "Файл не найден"}})
            return httpx.Response(200, json=[out(f)])
        return httpx.Response(200, json={i: out(self.files[i], f"http://s3/{i}") for i in body["file_ids"] if i in self.files})

    def classroom(self, request: httpx.Request) -> httpx.Response:
        group = self.groups.get(request.url.path.rsplit("/", 1)[1])
        if group is None or group["teacher_id"] != request.url.params["teacher_id"]:
            return httpx.Response(404, json={"error": {"code": "group_not_found", "message": "Нет"}})
        return httpx.Response(200, json=group)


@pytest.fixture
def fakes() -> FakeServices:
    f = FakeServices()
    media.transport = httpx.MockTransport(f.media)
    classroom.transport = httpx.MockTransport(f.classroom)
    assessment.transport = httpx.MockTransport(f.assessment)
    return f


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
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables if t.name != "subjects")
    async with db.engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def apply(handler, type_: str, **data) -> None:
    async with db.sessionmaker() as s, s.begin():
        await handler(make_envelope(type_, {k: str(v) if isinstance(v, UUID) else v for k, v in data.items()}), s)


async def link(teacher: UUID, student_id: UUID) -> None:
    await apply(handlers.on_classroom_event, "classroom.link.created", teacher_id=teacher, student_id=student_id, link_id=uuid4())


async def outbox(key: str) -> list[dict]:
    async with db.engine.connect() as conn:
        rows = await conn.execute(text("SELECT payload FROM outbox WHERE routing_key = :k ORDER BY created_at"), {"k": key})
        return [r[0] for r in rows]
