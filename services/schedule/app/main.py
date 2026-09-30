from contextlib import asynccontextmanager

from fastapi import FastAPI
from testmatica_common.errors import install_error_handlers
from testmatica_common.logging import configure_logging
from testmatica_common.messaging import EVENTS_EXCHANGE
from testmatica_common.service import ServiceRuntime, health_router

from . import handlers, people, subjects_sync
from .api import internal, lessons, requests
from .config import settings
from .deps import db

configure_logging(settings.service_name, settings.log_level)

runtime = ServiceRuntime(settings, db)
runtime.consumer("schedule.subjects", [(EVENTS_EXCHANGE, "content.subject.updated")], subjects_sync.on_subject_updated)
runtime.consumer("schedule.identity", [(EVENTS_EXCHANGE, "identity.user.*")], people.on_identity_event)
runtime.consumer(
    "schedule.classroom",
    [
        (EVENTS_EXCHANGE, "classroom.member.*"),
        (EVENTS_EXCHANGE, "classroom.link.ended"),
        (EVENTS_EXCHANGE, "classroom.group.updated"),
    ],
    handlers.on_classroom_event,
)
runtime.every("reminders", settings.jobs_interval_seconds, handlers.run_due_jobs)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(
    title="ТестМатика · schedule", version="0.1.0", lifespan=lifespan, root_path=settings.root_path,
    openapi_url=settings.openapi_url,
)
install_error_handlers(app)
app.include_router(health_router(db))
app.include_router(lessons.router)
app.include_router(requests.router)
app.include_router(internal.router)
