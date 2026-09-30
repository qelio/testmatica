from contextlib import asynccontextmanager

from fastapi import FastAPI
from testmatica_common.errors import install_error_handlers
from testmatica_common.logging import configure_logging
from testmatica_common.messaging import EVENTS_EXCHANGE
from testmatica_common.service import ServiceRuntime, health_router

from . import deals, people, subjects_sync
from .api import groups, internal, invitations, me, students
from .config import settings
from .deps import db

configure_logging(settings.service_name, settings.log_level)

runtime = ServiceRuntime(settings, db)
runtime.consumer("classroom.subjects", [(EVENTS_EXCHANGE, "content.subject.updated")], subjects_sync.on_subject_updated)
runtime.consumer("classroom.identity", [(EVENTS_EXCHANGE, "identity.user.*")], people.on_identity_event)
runtime.consumer(
    "classroom.marketplace",
    [
        (EVENTS_EXCHANGE, "marketplace.deal.agreed"),
        (EVENTS_EXCHANGE, "marketplace.group_offer.started"),
        (EVENTS_EXCHANGE, "marketplace.group_offer.joined"),
    ],
    deals.on_marketplace_event,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(
    title="ТестМатика · classroom", version="0.1.0", lifespan=lifespan, root_path=settings.root_path
)
install_error_handlers(app)
app.include_router(health_router(db))
app.include_router(groups.router)
app.include_router(students.router)
app.include_router(invitations.router)
app.include_router(me.router)
app.include_router(internal.router)
