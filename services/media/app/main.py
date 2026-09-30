from contextlib import asynccontextmanager

from fastapi import FastAPI
from testmatica_common.errors import install_error_handlers
from testmatica_common.logging import configure_logging
from testmatica_common.service import ServiceRuntime, health_router

from . import storage
from .api import files, internal
from .config import settings
from .deps import db

configure_logging(settings.service_name, settings.log_level)

runtime = ServiceRuntime(settings, db)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await storage.ensure_bucket()
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(title="ТестМатика · media", version="0.1.0", lifespan=lifespan, root_path=settings.root_path, openapi_url=settings.openapi_url)
install_error_handlers(app)
app.include_router(health_router(db))
app.include_router(files.router)
app.include_router(internal.router)
