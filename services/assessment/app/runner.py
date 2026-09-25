"""Проверка кода: команда assessment.code.check → песочница code-runner → результат в отправке."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError
from testmatica_common.messaging import Envelope

from .deps import code_runner, outbox
from .models import CHECKING, CORRECT, ERROR, INCORRECT, Submission, Task

# Что видит ученик вместо подробностей: номер упавшего теста и вид ошибки (без входных данных — ТЗ).
FAILURES = {"wrong_answer", "runtime_error", "time_limit", "memory_limit"}


async def on_code_check(envelope: Envelope, session: AsyncSession) -> None:
    sub = await session.get(Submission, UUID(envelope.data["submission_id"]), with_for_update=True)
    if sub is None or sub.status != CHECKING:
        return
    task = await session.get(Task, sub.task_id)
    try:
        result = await code_runner.post(
            "/run",
            json={
                "language": task.language or "python",
                "code": sub.answer["code"],
                "tests": [{"input": c.input, "expected": c.expected} for c in task.tests],
                "time_limit_s": task.time_limit_s or 2,
                "memory_limit_mb": task.memory_limit_mb or 128,
            },
        )
    except ApiError:
        # Песочница недоступна — ученик увидит «ошибка проверки» и сможет отправить решение снова.
        sub.status, sub.checked_at = ERROR, datetime.now(UTC)
        return

    cases = result["cases"]
    sub.run_log = cases  # выводы и ошибки по каждому тесту — педагогу
    failed = next((c for c in cases if c["status"] != "passed"), None)
    sub.status = CORRECT if result["passed"] else INCORRECT
    sub.score = 1.0 if result["passed"] else 0.0
    sub.failed_case = failed["number"] if failed else None
    sub.failure = failed["status"] if failed and failed["status"] in FAILURES else None
    sub.checked_at = datetime.now(UTC)
    await outbox.event(
        session,
        "assessment.submission.checked",
        {"submission_id": str(sub.id), "task_id": str(task.id), "student_id": str(sub.student_id), "status": sub.status,
         "context_type": sub.context_type, "context_id": str(sub.context_id)},
        actor_id=sub.student_id,
    )
