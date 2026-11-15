"""Проверка кода: команда assessment.code.check → песочница code-runner → результат в отправке."""

from datetime import UTC, datetime
from io import StringIO
from tokenize import NAME, TokenError, generate_tokens
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError
from testmatica_common.messaging import Envelope

from . import attempts
from .deps import code_runner, outbox
from .models import CHECKING, CORRECT, ERROR, INCORRECT, Submission, Task

FAILURES = {"wrong_answer", "runtime_error", "time_limit", "memory_limit"}


def _forbidden_word(code: str, forbidden_words: list[str]) -> str | None:
    if not forbidden_words:
        return None
    forbidden = set(forbidden_words)
    try:
        return next(
            (token.string for token in generate_tokens(StringIO(code).readline)
             if token.type == NAME and token.string in forbidden),
            None,
        )
    except (TokenError, SyntaxError):
        # Синтаксическую ошибку обработает обычная проверка программы.
        return None


async def on_code_check(envelope: Envelope, session: AsyncSession) -> None:
    sub = await session.get(Submission, UUID(envelope.data["submission_id"]), with_for_update=True)
    if sub is None or sub.status != CHECKING:
        return
    task = await session.get(Task, sub.task_id)
    sub.forbidden_word = _forbidden_word(sub.answer["code"], task.forbidden_words)
    if sub.forbidden_word:
        sub.status, sub.score = INCORRECT, 0.0
    else:
        try:
            await _run_tests(sub, task)
        except ApiError:
            # При недоступности песочницы решение можно отправить на проверку повторно.
            sub.status, sub.checked_at = ERROR, datetime.now(UTC)
            await attempts.on_submission_changed(session, sub)
            return
    sub.checked_at = datetime.now(UTC)
    await outbox.event(
        session,
        "assessment.submission.checked",
        {"submission_id": str(sub.id), "task_id": str(task.id), "student_id": str(sub.student_id), "status": sub.status,
         "context_type": sub.context_type, "context_id": str(sub.context_id)},
        actor_id=sub.student_id,
    )
    await attempts.on_submission_changed(session, sub)


async def _run_tests(sub: Submission, task: Task) -> None:
    tests = [{"input": case.input, "expected": case.expected} for case in task.tests]
    result = await code_runner.post(
        "/run",
        json={
            "language": task.language or "python",
            "code": sub.answer["code"],
            "tests": tests,
            "time_limit_s": task.time_limit_s or 2,
            "memory_limit_mb": task.memory_limit_mb or 128,
        },
    )
    cases = result["cases"]
    sub.run_log = cases
    failed = next((case for case in cases if case["status"] != "passed"), None)
    sub.status = CORRECT if result["passed"] else INCORRECT
    sub.score = 1.0 if result["passed"] else 0.0
    if failed:
        number = failed["number"]
        sub.failed_case = number
        sub.failure = failed["status"] if failed["status"] in FAILURES else None
        if task.show_failed_test and 1 <= number <= len(tests):
            sub.failed_test = {"number": number, **tests[number - 1], "output": failed["output"]}
