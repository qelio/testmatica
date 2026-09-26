import os

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://redis:6379/14")
os.environ["RUN_BACKGROUND"] = "false"

from uuid import UUID, uuid4  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from testmatica_common.testing import TestTokens, make_envelope  # noqa: E402

from app import relations  # noqa: E402
from app.config import settings  # noqa: E402
from app.deps import auth, db, redis, verifier  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

tokens = TestTokens()
auth.verifier = tokens.verifier(settings.jwt_issuer, settings.jwt_audience)
# WebSocket проверяет токен тем же ключом.
verifier._keys = auth.verifier._keys
verifier._fetched_at = float("inf")


def token(user_id: UUID, roles=("student",)) -> str:
    return tokens.issue(user_id, list(roles), settings.jwt_issuer, settings.jwt_audience)


def bearer(user_id: UUID, roles=("student",)) -> dict:
    return {"Authorization": f"Bearer {token(user_id, roles)}"}


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


async def event(type_: str, **data) -> None:
    """Применить событие identity/classroom к репликам чата."""
    envelope = make_envelope(type_, {k: str(v) if isinstance(v, UUID) else v for k, v in data.items()})
    handler = relations.on_identity_event if type_.startswith("identity.") else relations.on_classroom_event
    async with db.sessionmaker() as s, s.begin():
        await handler(envelope, s)


async def person(name: str, roles=("student",)) -> UUID:
    uid = uuid4()
    await event("identity.user.registered", user_id=uid, full_name=name, login=None, roles=list(roles))
    return uid


@pytest.fixture
async def school():
    """Педагог Мария, класс 7А с Аней и Петей; Оля — индивидуальная ученица Марии; Вася — посторонний."""
    maria = await person("Мария Ивановна", ("teacher",))
    anya, petya, olya, vasya = [await person(n) for n in ("Аня", "Петя", "Оля", "Вася")]
    gid = uuid4()
    await event("classroom.group.created", group_id=gid, teacher_id=maria, title="7А", paid=False)
    for sid in (anya, petya, olya):
        await event("classroom.link.created", link_id=uuid4(), teacher_id=maria, student_id=sid, source="manual", student_name="")
    for sid in (anya, petya):
        await event("classroom.member.added", group_id=gid, teacher_id=maria, student_id=sid)
    return {"maria": maria, "anya": anya, "petya": petya, "olya": olya, "vasya": vasya, "gid": gid}


async def outbox(routing_key: str) -> list[dict]:
    async with db.engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT payload FROM outbox WHERE routing_key = :k ORDER BY created_at"), {"k": routing_key}
        )
        return [r[0] for r in rows]


class FakeMedia:
    """Имитация внутреннего API media: файлы с владельцами и назначением."""

    def __init__(self) -> None:
        self.files: dict[str, dict] = {}

    def add(self, owner: UUID, filename="решение.pdf", purpose="chat_attachment") -> str:
        fid = str(uuid4())
        self.files[fid] = {"id": fid, "owner": str(owner), "purpose": purpose, "filename": filename,
                           "mime": "application/pdf", "size": 1234}
        return fid

    def handle(self, request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        public = lambda f, url=None: {k: f[k] for k in ("id", "filename", "mime", "size")} | {  # noqa: E731
            "purpose": f["purpose"], "created_at": "2026-09-24T00:00:00Z", "url": url}
        if request.url.path == "/internal/files/claim":
            out = []
            for fid in body["file_ids"]:
                f = self.files.get(fid)
                if f is None or f["owner"] != body["owner_id"] or f["purpose"] != body["purpose"]:
                    return httpx.Response(422, json={"error": {"code": "invalid_attachment", "message": "Файл не найден"}})
                out.append(public(f))
            return httpx.Response(200, json=out)
        return httpx.Response(
            200, json={fid: public(self.files[fid], f"http://s3/{fid}") for fid in body["file_ids"] if fid in self.files}
        )


@pytest.fixture
def fake_media() -> FakeMedia:
    from app.deps import media

    fake = FakeMedia()
    media.transport = httpx.MockTransport(fake.handle)
    return fake
