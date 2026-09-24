import os
import subprocess

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

tokens = TestTokens()
auth.verifier = tokens.verifier(settings.jwt_issuer, settings.jwt_audience)


def bearer(user_id, roles) -> dict:
    token = tokens.issue(user_id, list(roles), settings.jwt_issuer, settings.jwt_audience)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session", autouse=True)
async def schema():
    # Здесь схема создаётся настоящими миграциями: нужно проверить триггер неизменяемости.
    async with db.engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=os.environ)
    yield
    await db.dispose()


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def audit_consumer() -> Consumer:
    return Consumer(Broker("amqp://unused"), db, "audit.events", [], handlers.on_event)
