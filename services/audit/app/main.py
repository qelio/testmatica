from contextlib import asynccontextmanager

from fastapi import FastAPI
from testmatica_common.errors import install_error_handlers
from testmatica_common.logging import configure_logging
from testmatica_common.messaging import EVENTS_EXCHANGE
from testmatica_common.service import ServiceRuntime, health_router

from . import handlers
from .api import audit
from .config import settings
from .deps import db

configure_logging(settings.service_name, settings.log_level)

runtime = ServiceRuntime(settings, db)
# «#» — все события всех сервисов.
runtime.consumer("audit.events", [(EVENTS_EXCHANGE, "#")], handlers.on_event, prefetch=50)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(
    title="ТестМатика · audit", version="0.1.0", lifespan=lifespan, root_path=settings.root_path
)
install_error_handlers(app)
app.include_router(health_router(db))
app.include_router(audit.router)
