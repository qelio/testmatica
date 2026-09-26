from contextlib import asynccontextmanager

from fastapi import FastAPI
from testmatica_common.errors import install_error_handlers
from testmatica_common.logging import configure_logging
from testmatica_common.messaging import EVENTS_EXCHANGE
from testmatica_common.service import ServiceRuntime, health_router

from . import handlers, subjects_sync
from .api import competencies, requests, tutors
from .config import settings
from .deps import db

configure_logging(settings.service_name, settings.log_level)

runtime = ServiceRuntime(settings, db)
runtime.consumer("marketplace.subjects", [(EVENTS_EXCHANGE, "content.subject.updated")], subjects_sync.on_subject_updated)
runtime.consumer("marketplace.identity", [(EVENTS_EXCHANGE, "identity.user.*")], handlers.on_identity_event)
runtime.consumer("marketplace.moderation", [(EVENTS_EXCHANGE, "moderation.decision.made")], handlers.on_moderation_decision)
runtime.every("expire_requests", 600, requests.expire_requests)
runtime.every("default_competencies", 300, competencies.ensure_defaults)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(title="Тестматика · marketplace", version="0.1.0", lifespan=lifespan, root_path=settings.root_path)
install_error_handlers(app)
app.include_router(health_router(db))
app.include_router(tutors.router)
app.include_router(requests.router)
app.include_router(competencies.router)
