import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from testmatica_common.errors import install_error_handlers
from testmatica_common.logging import configure_logging
from testmatica_common.messaging import EVENTS_EXCHANGE
from testmatica_common.service import ServiceRuntime, health_router

from . import people, rooms, storage
from .api import internal, proctoring, recordings
from .api import rooms as rooms_api
from .config import settings
from .deps import db

configure_logging(settings.service_name, settings.log_level)
log = logging.getLogger(__name__)

runtime = ServiceRuntime(settings, db)
runtime.consumer("video.identity", [(EVENTS_EXCHANGE, "identity.user.*")], people.on_identity_event)
# Лимит бесплатного занятия и срок хранения записей.
runtime.every("room_limits", 15, rooms.enforce_limits)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.run_background:
        try:
            await storage.ensure_bucket()  # egress пишет в эту корзину
        except Exception:
            log.exception("recordings bucket not ready")
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(title="ТестМатика · video", version="0.1.0", lifespan=lifespan, root_path=settings.root_path)
install_error_handlers(app)
app.include_router(health_router(db))
app.include_router(rooms_api.router)
app.include_router(recordings.router)
app.include_router(proctoring.router)
app.include_router(internal.router)
