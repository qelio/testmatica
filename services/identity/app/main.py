from contextlib import asynccontextmanager

from fastapi import FastAPI
from testmatica_common.errors import install_error_handlers
from testmatica_common.logging import configure_logging
from testmatica_common.service import ServiceRuntime, health_router

from .api import auth, me
from .config import settings
from .deps import db, redis, signing_key

configure_logging(settings.service_name, settings.log_level)

runtime = ServiceRuntime(settings, db)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield
    await runtime.stop()
    await redis.aclose()


app = FastAPI(
    title="Тестматика · identity", version="0.1.0", lifespan=lifespan, root_path=settings.root_path
)
install_error_handlers(app)
app.include_router(health_router(db))
app.include_router(auth.router)
app.include_router(me.router)


@app.get("/.well-known/jwks.json", tags=["auth"])
async def jwks() -> dict:
    """Публичные ключи для проверки JWT другими сервисами."""
    return signing_key.jwks
