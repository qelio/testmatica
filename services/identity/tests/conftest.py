import os

# Тесты работают с отдельной базой <svc>_test и отдельной базой Redis; брокер не нужен.
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://redis:6379/15")
os.environ["RUN_BACKGROUND"] = "false"
os.environ["JWT_PRIVATE_KEY_PATH"] = "/tmp/testmatica-test-keys/jwt.pem"
os.environ["REFRESH_COOKIE_PATH"] = "/auth"

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.deps import db, redis  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

PASSWORD = "secret-pass-1"


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
    await redis.flushdb()


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app, client=("10.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def sent_code(email: str, template: str) -> str:
    """Код из последней команды на отправку письма (в тестах брокера нет — читаем outbox)."""
    async with db.engine.connect() as conn:
        payload = (
            await conn.execute(
                text(
                    "SELECT payload FROM outbox WHERE routing_key = 'notification.email' "
                    "AND payload->'data'->>'to' = :to AND payload->'data'->>'template' = :tpl "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"to": email.lower(), "tpl": template},
            )
        ).scalar_one()
    return payload["data"]["params"]["code"]


async def events(type_: str) -> list[dict]:
    async with db.engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT payload FROM outbox WHERE routing_key = :t ORDER BY created_at"), {"t": type_}
        )
        return [r[0] for r in rows]


async def register(client: httpx.AsyncClient, email: str, role: str = "student", verify: bool = True) -> dict:
    resp = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "full_name": "Иван Петров",
            "role": role,
            "consent_pdn": True, "accept_terms": True,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    if verify:
        code = await sent_code(email, "email_verification")
        resp = await client.post("/auth/verify-email", json={"challenge_id": body["challenge_id"], "code": code})
        assert resp.status_code == 200, resp.text
    return body


async def login(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> dict:
    resp = await client.post("/auth/login", json={"identifier": email, "password": password})
    assert resp.status_code == 200, resp.text
    challenge = resp.json()
    assert challenge["status"] == "2fa_required"
    code = await sent_code(email, "login")
    resp = await client.post("/auth/login/verify", json={"challenge_id": challenge["challenge_id"], "code": code})
    assert resp.status_code == 200, resp.text
    return resp.json()
