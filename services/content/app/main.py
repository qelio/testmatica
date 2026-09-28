from contextlib import asynccontextmanager

from fastapi import FastAPI
from testmatica_common.errors import install_error_handlers
from testmatica_common.logging import configure_logging
from testmatica_common.messaging import EVENTS_EXCHANGE
from testmatica_common.service import ServiceRuntime, health_router

from . import handlers
from .api import admin, catalog, editor, learning, subjects
from .config import settings
from .deps import db

configure_logging(settings.service_name, settings.log_level)

runtime = ServiceRuntime(settings, db)
runtime.consumer("content.identity", [(EVENTS_EXCHANGE, "identity.user.*")], handlers.on_identity_event)
runtime.consumer("content.classroom", [(EVENTS_EXCHANGE, "classroom.link.*")], handlers.on_classroom_event)
runtime.consumer(
    "content.moderation", [(EVENTS_EXCHANGE, "moderation.decision.made")], handlers.on_moderation_decision
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(title="Тестматика · content", version="0.1.0", lifespan=lifespan, root_path=settings.root_path)
install_error_handlers(app)
app.include_router(health_router(db))
app.include_router(subjects.router)
app.include_router(catalog.router)
app.include_router(learning.router)
app.include_router(editor.router)
app.include_router(admin.router)
