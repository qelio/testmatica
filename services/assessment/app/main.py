from contextlib import asynccontextmanager

from fastapi import FastAPI
from testmatica_common.errors import install_error_handlers
from testmatica_common.logging import configure_logging
from testmatica_common.messaging import COMMANDS_EXCHANGE, EVENTS_EXCHANGE
from testmatica_common.service import ServiceRuntime, health_router

from . import attempts, handlers, rubric, runner, subjects_sync
from .api import admin, assignments, course_tests, exams, game, internal, quizzes, solving, tasks, topics
from .config import settings
from .deps import db

configure_logging(settings.service_name, settings.log_level)

runtime = ServiceRuntime(settings, db)
runtime.consumer("assessment.subjects", [(EVENTS_EXCHANGE, "content.subject.updated")], subjects_sync.on_subject_updated)
runtime.consumer("assessment.identity", [(EVENTS_EXCHANGE, "identity.user.*")], handlers.on_identity_event)
runtime.consumer("assessment.classroom", [(EVENTS_EXCHANGE, "classroom.link.*")], handlers.on_classroom_event)
runtime.consumer("assessment.content", [(EVENTS_EXCHANGE, "content.course.*")], handlers.on_content_event)
runtime.consumer("assessment.video", [(EVENTS_EXCHANGE, "video.proctor.screen")], handlers.on_video_event)
runtime.consumer("assessment.schedule", [(EVENTS_EXCHANGE, "schedule.lesson.deleted")], handlers.on_schedule_event)
runtime.consumer("assessment.moderation", [(EVENTS_EXCHANGE, "moderation.decision.made")], handlers.on_moderation_decision)
# Проверка кода — по одной за раз на экземпляр: песочница выполняет запуски последовательно.
runtime.consumer("assessment.code", [(COMMANDS_EXCHANGE, "assessment.code")], runner.on_code_check, prefetch=1)
runtime.every("default_topics", 300, rubric.ensure_default_topics)
# Сдать попытки с истёкшим таймером или дедлайном, даже если ученик закрыл вкладку.
runtime.every("expire_attempts", 10, attempts.expire_job)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(title="ТестМатика · assessment", version="0.1.0", lifespan=lifespan, root_path=settings.root_path, openapi_url=settings.openapi_url)
install_error_handlers(app)
app.include_router(health_router(db))
app.include_router(topics.router)
app.include_router(exams.router)
app.include_router(game.router)
app.include_router(quizzes.router)
app.include_router(assignments.router)
app.include_router(course_tests.router)
app.include_router(tasks.router)
app.include_router(solving.router)
app.include_router(internal.router)
app.include_router(admin.router)
