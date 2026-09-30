from contextlib import asynccontextmanager

from fastapi import FastAPI
from testmatica_common.errors import install_error_handlers
from testmatica_common.logging import configure_logging
from testmatica_common.service import ServiceRuntime, health_router

from . import subscriptions
from .api import admin, subscription
from .config import settings
from .deps import db

configure_logging(settings.service_name, settings.log_level)

runtime = ServiceRuntime(settings, db)
runtime.every("subscriptions", 300, subscriptions.tick)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(title="ТестМатика · billing", version="0.1.0", lifespan=lifespan, root_path=settings.root_path, openapi_url=settings.openapi_url)
install_error_handlers(app)
app.include_router(health_router(db))
app.include_router(subscription.router)
app.include_router(subscription.internal)
app.include_router(admin.router)
