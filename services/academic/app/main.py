from contextlib import asynccontextmanager

from fastapi import FastAPI
from testmatica_common.errors import install_error_handlers
from testmatica_common.logging import configure_logging
from testmatica_common.messaging import EVENTS_EXCHANGE
from testmatica_common.service import ServiceRuntime, health_router

from . import moderation, people, schedule_sync, subjects_sync, test_grades
from .api import analytics, grade_types, journal, me, planning
from .config import settings
from .deps import db

configure_logging(settings.service_name, settings.log_level)

runtime = ServiceRuntime(settings, db)
runtime.consumer("academic.subjects", [(EVENTS_EXCHANGE, "content.subject.updated")], subjects_sync.on_subject_updated)
runtime.consumer("academic.identity", [(EVENTS_EXCHANGE, "identity.user.*")], people.on_identity_event)
runtime.consumer(
    "academic.assessment",
    [(EVENTS_EXCHANGE, "assessment.attempt.graded"), (EVENTS_EXCHANGE, "assessment.assignment.deleted"),
     (EVENTS_EXCHANGE, "assessment.assignment.students_removed")],
    test_grades.on_assessment_event,
)
# Старые оценки за тесты — по журналам предметов (решение №59); после разноски запросов почти нет.
runtime.every("test-grade-subjects", 6 * 3600, test_grades.backfill_subjects)
runtime.consumer("academic.schedule", [(EVENTS_EXCHANGE, "schedule.lesson.deleted")], schedule_sync.on_schedule_event)
runtime.consumer("academic.moderation", [(EVENTS_EXCHANGE, "moderation.decision.made")], moderation.on_moderation_decision)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(
    title="ТестМатика · academic", version="0.1.0", lifespan=lifespan, root_path=settings.root_path,
    openapi_url=settings.openapi_url,
)
install_error_handlers(app)
app.include_router(health_router(db))
app.include_router(grade_types.router)
app.include_router(journal.router)
app.include_router(me.router)
app.include_router(planning.router)
app.include_router(analytics.router)
