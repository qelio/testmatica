import os

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["RUN_BACKGROUND"] = "false"
# Тесты работают с настоящим S3 (SeaweedFS), но в отдельной корзине.
os.environ["S3_BUCKET"] = "testmatica-test"

from uuid import UUID  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from testmatica_common.internal import INTERNAL_HEADER  # noqa: E402
from testmatica_common.testing import TestTokens  # noqa: E402

from app import storage  # noqa: E402
from app.config import settings  # noqa: E402
from app.deps import auth, db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

tokens = TestTokens()
auth.verifier = tokens.verifier(settings.jwt_issuer, settings.jwt_audience)
INTERNAL = {INTERNAL_HEADER: settings.internal_token}


def bearer(user_id: UUID) -> dict:
    return {"Authorization": f"Bearer {tokens.issue(user_id, ['student'], settings.jwt_issuer, settings.jwt_audience)}"}


@pytest.fixture(scope="session", autouse=True)
async def schema():
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await storage.ensure_bucket()
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


async def upload(client, user, name="решение.pdf", content=b"%PDF-1.4 test", purpose="answer"):
    return await client.post(
        "/files", files={"file": (name, content, "application/x-whatever")}, data={"purpose": purpose}, headers=bearer(user)
    )
