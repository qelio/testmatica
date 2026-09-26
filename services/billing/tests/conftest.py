import os

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["RUN_BACKGROUND"] = "false"

from uuid import UUID  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from testmatica_common.testing import TestTokens  # noqa: E402

from app.config import settings  # noqa: E402
from app.deps import auth, db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

tokens = TestTokens()
auth.verifier = tokens.verifier(settings.jwt_issuer, settings.jwt_audience)
INTERNAL = {"X-Internal-Token": settings.internal_token}


def bearer(user_id: UUID, roles=("teacher",)) -> dict:
    return {"Authorization": f"Bearer {tokens.issue(user_id, list(roles), settings.jwt_issuer, settings.jwt_audience)}"}


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


async def outbox(key: str) -> list[dict]:
    async with db.engine.connect() as conn:
        rows = await conn.execute(text("SELECT payload FROM outbox WHERE routing_key = :k ORDER BY created_at"), {"k": key})
        return [r[0] for r in rows]


async def sql(query: str, **params) -> None:
    async with db.engine.begin() as conn:
        await conn.execute(text(query), params)
