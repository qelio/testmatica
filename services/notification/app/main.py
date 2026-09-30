from contextlib import asynccontextmanager

from fastapi import FastAPI
from testmatica_common.errors import install_error_handlers
from testmatica_common.logging import configure_logging
from testmatica_common.messaging import COMMANDS_EXCHANGE, EVENTS_EXCHANGE
from testmatica_common.service import ServiceRuntime, health_router

from . import handlers
from .api import notifications
from .config import settings
from .deps import db

configure_logging(settings.service_name, settings.log_level)

runtime = ServiceRuntime(settings, db)
runtime.consumer("notification.email", [(COMMANDS_EXCHANGE, "notification.email")], handlers.on_email_command)
runtime.consumer("notification.inapp", [(COMMANDS_EXCHANGE, "notification.inapp")], handlers.on_inapp_command)
runtime.consumer("notification.identity", [(EVENTS_EXCHANGE, "identity.user.*")], handlers.on_identity_event)
runtime.consumer("notification.classroom", [(EVENTS_EXCHANGE, "classroom.link.*")], handlers.on_classroom_event)
runtime.consumer("notification.video", [(EVENTS_EXCHANGE, "video.recording.ready")], handlers.on_video_event)
runtime.consumer(
    "notification.marketplace",
    [
        (EVENTS_EXCHANGE, "marketplace.education.approved"),
        (EVENTS_EXCHANGE, "marketplace.education.rejected"),
        (EVENTS_EXCHANGE, "marketplace.request.*"),
        (EVENTS_EXCHANGE, "marketplace.response.created"),
        (EVENTS_EXCHANGE, "marketplace.response.closed"),
        (EVENTS_EXCHANGE, "marketplace.deal.agreed"),
        (EVENTS_EXCHANGE, "marketplace.review.approved"),
        (EVENTS_EXCHANGE, "marketplace.review.rejected"),
        (EVENTS_EXCHANGE, "marketplace.review.removed"),
        (EVENTS_EXCHANGE, "marketplace.review.reply_approved"),
        (EVENTS_EXCHANGE, "marketplace.review.reply_rejected"),
        (EVENTS_EXCHANGE, "marketplace.review.dispute_resolved"),
        (EVENTS_EXCHANGE, "marketplace.group_offer.*"),
        (EVENTS_EXCHANGE, "marketplace.profile.blocked"),
        (EVENTS_EXCHANGE, "marketplace.trial.*"),
    ],
    handlers.on_marketplace_event,
)
runtime.consumer(
    "notification.billing",
    [
        (EVENTS_EXCHANGE, "billing.subscription.changed"),
        (EVENTS_EXCHANGE, "billing.subscription.expiring"),
        (EVENTS_EXCHANGE, "billing.payment.failed"),
    ],
    handlers.on_billing_event,
)
runtime.consumer(
    "notification.academic",
    [(EVENTS_EXCHANGE, "academic.grade.*"), (EVENTS_EXCHANGE, "academic.plan_template.*")],
    handlers.on_academic_event,
)
runtime.consumer("notification.content", [(EVENTS_EXCHANGE, "content.course.*")], handlers.on_content_event)
runtime.consumer(
    "notification.assessment",
    [(EVENTS_EXCHANGE, "assessment.task.*"), (EVENTS_EXCHANGE, "assessment.submission.reviewed"),
     (EVENTS_EXCHANGE, "assessment.assignment.*"), (EVENTS_EXCHANGE, "assessment.attempt.graded")],
    handlers.on_assessment_event,
)
runtime.consumer(
    "notification.schedule",
    [(EVENTS_EXCHANGE, "schedule.lesson.*"), (EVENTS_EXCHANGE, "schedule.reschedule.*")],
    handlers.on_schedule_event,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(
    title="ТестМатика · notification", version="0.1.0", lifespan=lifespan, root_path=settings.root_path,
    openapi_url=settings.openapi_url,
)
install_error_handlers(app)
app.include_router(health_router(db))
app.include_router(notifications.router)
