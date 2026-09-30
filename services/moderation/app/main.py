from contextlib import asynccontextmanager

from fastapi import FastAPI
from testmatica_common.errors import install_error_handlers
from testmatica_common.logging import configure_logging
from testmatica_common.messaging import EVENTS_EXCHANGE
from testmatica_common.service import ServiceRuntime, health_router

from . import api, handlers
from .config import settings
from .deps import db

configure_logging(settings.service_name, settings.log_level)

runtime = ServiceRuntime(settings, db)
runtime.consumer("moderation.identity", [(EVENTS_EXCHANGE, "identity.user.*")], handlers.on_identity_event)
runtime.consumer("moderation.content", [(EVENTS_EXCHANGE, "content.course.*")], handlers.on_content_event)
runtime.consumer("moderation.assessment", [(EVENTS_EXCHANGE, "assessment.task.*")], handlers.on_assessment_event)
runtime.consumer("moderation.academic", [(EVENTS_EXCHANGE, "academic.plan_template.*")], handlers.on_academic_event)
runtime.consumer("moderation.billing", [(EVENTS_EXCHANGE, "billing.subscription.changed")], handlers.on_billing_event)
runtime.consumer("moderation.marketplace", [(EVENTS_EXCHANGE, "marketplace.education.*"), (EVENTS_EXCHANGE, "marketplace.review.*")], handlers.on_marketplace_event)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(title="ТестМатика · moderation", version="0.1.0", lifespan=lifespan, root_path=settings.root_path, openapi_url=settings.openapi_url)
install_error_handlers(app)
app.include_router(health_router(db))
app.include_router(api.router)
