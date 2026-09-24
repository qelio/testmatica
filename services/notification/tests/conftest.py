import os

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["RUN_BACKGROUND"] = "false"

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from testmatica_common.messaging import Broker, Consumer  # noqa: E402
from testmatica_common.testing import TestTokens  # noqa: E402

from app import handlers  # noqa: E402
from app.config import settings  # noqa: E402
from app.deps import auth, db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

tokens = TestTokens()
auth.verifier = tokens.verifier(settings.jwt_issuer, settings.jwt_audience)


def bearer(user_id, roles=("student",)) -> dict:
    token = tokens.issue(user_id, list(roles), settings.jwt_issuer, settings.jwt_audience)
    return {"Authorization": f"Bearer {token}"}


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
def sent_emails(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    async def fake_send(to, subject, text, html):
        sent.append({"to": to, "subject": subject, "text": text, "html": html})

    monkeypatch.setattr(handlers.mailer, "send_email", fake_send)
    return sent


def consumer(queue: str, handler) -> Consumer:
    """Consumer без подключения к брокеру — вызываем process() напрямую."""
    return Consumer(Broker("amqp://unused"), db, queue, [], handler)
