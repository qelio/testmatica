from contextlib import asynccontextmanager

from fastapi import FastAPI
from testmatica_common.errors import install_error_handlers
from testmatica_common.logging import configure_logging
from testmatica_common.messaging import EVENTS_EXCHANGE
from testmatica_common.service import ServiceRuntime, health_router

from . import realtime, relations
from .api import conversations
from .config import settings
from .deps import db, redis

configure_logging(settings.service_name, settings.log_level)

runtime = ServiceRuntime(settings, db)
runtime.consumer("chat.identity", [(EVENTS_EXCHANGE, "identity.user.*")], relations.on_identity_event)
runtime.consumer(
    "chat.classroom",
    [
        (EVENTS_EXCHANGE, "classroom.group.*"),
        (EVENTS_EXCHANGE, "classroom.member.*"),
        (EVENTS_EXCHANGE, "classroom.link.*"),
    ],
    relations.on_classroom_event,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield
    await runtime.stop()
    await redis.aclose()


app = FastAPI(title="Тестматика · chat", version="0.1.0", lifespan=lifespan, root_path=settings.root_path)
install_error_handlers(app)
app.include_router(health_router(db))
app.include_router(conversations.router)
app.include_router(realtime.router)
