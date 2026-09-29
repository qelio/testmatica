import os

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["RUN_BACKGROUND"] = "false"

import json  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402
from uuid import UUID, uuid4  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from testmatica_common.testing import TestTokens, make_envelope  # noqa: E402

from app import handlers, profiles  # noqa: E402
from app.config import settings  # noqa: E402
from app.deps import auth, classroom, content, db, identity, media  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

tokens = TestTokens()
auth.verifier = tokens.verifier(settings.jwt_issuer, settings.jwt_audience)

MATH, PHYSICS = str(uuid4()), str(uuid4())


def bearer(user_id: UUID, roles=("teacher",)) -> dict:
    return {"Authorization": f"Bearer {tokens.issue(user_id, list(roles), settings.jwt_issuer, settings.jwt_audience)}"}


class Fakes:
    def __init__(self) -> None:
        self.files: dict[str, dict] = {}
        self.seen: dict[str, str] = {}
        self.links: set[tuple[str, str]] = set()  # (педагог, ученик)
        self.group_limited: set[str] = set()  # педагоги, упёршиеся в лимит групп
        self.avatars: dict[str, str | None] = {}  # фото, переданные в identity

    def link(self, teacher: UUID, student: UUID) -> None:
        self.links.add((str(teacher), str(student)))

    def file(self, owner: UUID, name="photo.jpg") -> str:
        fid = str(uuid4())
        self.files[fid] = {"id": fid, "owner": str(owner), "filename": name}
        return fid

    def online(self, user: UUID, minutes_ago: int = 1) -> None:
        self.seen[str(user)] = (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat()

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/subjects":
            return httpx.Response(200, json=[{"id": MATH, "name": "Математика"}, {"id": PHYSICS, "name": "Физика"}])
        if path == "/internal/group-limit":
            allowed = request.url.params["teacher_id"] not in self.group_limited
            return httpx.Response(200, json={"allowed": allowed, "message": None if allowed else "На бесплатном тарифе — до 3 активных групп"})
        if path == "/internal/links":
            key = (request.url.params["teacher_id"], request.url.params["student_id"])
            if key not in self.links:
                return httpx.Response(404, json={"error": {"code": "student_not_found", "message": "Не привязан"}})
            return httpx.Response(200, json={"teacher_id": key[0], "student_id": key[1], "active": True, "paid": False})
        body = json.loads(request.content) if request.content else {}
        if path == "/internal/users/presence":
            return httpx.Response(200, json={u: self.seen.get(u) for u in body["user_ids"]})
        if path.startswith("/internal/users/") and path.endswith("/avatar"):  # identity: фото профиля
            f = self.files.get(body["file_id"] or "")
            if body["file_id"] and (f is None or f["owner"] != path.split("/")[3]):
                return httpx.Response(422, json={"error": {"code": "invalid_attachment", "message": "Файл не найден"}})
            self.avatars[path.split("/")[3]] = body["file_id"]
            return httpx.Response(204)
        if path == "/internal/files/claim":
            out = []
            for fid in body["file_ids"]:
                f = self.files.get(fid)
                if f is None or f["owner"] != body["owner_id"]:
                    return httpx.Response(422, json={"error": {"code": "invalid_attachment", "message": "Файл не найден"}})
                out.append({"id": fid, "filename": f["filename"], "mime": "image/jpeg", "size": 10, "purpose": body["purpose"],
                            "created_at": "2026-09-26T00:00:00Z", "url": None})
            return httpx.Response(200, json=out)
        if path == "/internal/files/urls":
            return httpx.Response(200, json={i: {"id": i, "url": f"http://s3/{i}"} for i in body["file_ids"] if i in self.files})
        return httpx.Response(404)


@pytest.fixture(autouse=True)
def fakes() -> Fakes:
    f = Fakes()
    for client in (content, identity, media, classroom):
        client.transport = httpx.MockTransport(f.handle)
    profiles._subjects_cache = (0.0, {})
    return f


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


async def person(user_id: UUID, name: str, roles=("teacher",)) -> None:
    async with db.sessionmaker() as s, s.begin():
        await handlers.on_identity_event(make_envelope("identity.user.registered", {
            "user_id": str(user_id), "full_name": name, "roles": list(roles)}), s)


async def decide(kind: str, ref_id: str, decision: str, comment: str | None = None) -> None:
    async with db.sessionmaker() as s, s.begin():
        await handlers.on_moderation_decision(make_envelope("moderation.decision.made", {
            "kind": kind, "ref_id": ref_id, "decision": decision, "comment": comment, "moderator_id": str(uuid4())}), s)


async def outbox(key: str) -> list[dict]:
    async with db.engine.connect() as conn:
        rows = await conn.execute(text("SELECT payload FROM outbox WHERE routing_key = :k ORDER BY created_at"), {"k": key})
        return [r[0] for r in rows]
