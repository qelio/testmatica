"""Автопроверка: выбор ответа и короткий ответ. Код проверяет песочница (runner.py)."""

import re
from collections.abc import Iterable
from uuid import UUID

from .models import Task

MAX_ANSWER = 500
_NUMBER = re.compile(r"^[+-]?\d+([.,]\d+)?$")


def normalize(text: str) -> str:
    """Регистр, лишние пробелы, «ё», запятая в десятичных числах — не повод засчитать ошибку."""
    value = " ".join(text.strip().lower().replace("ё", "е").split())
    if _NUMBER.match(value):
        value = value.replace(",", ".")
        if "." in value:
            value = value.rstrip("0").rstrip(".") or "0"
    return value


def check_choice(task: Task, option_ids: Iterable[UUID]) -> bool:
    correct = {o.id for o in task.options if o.is_correct}
    return set(option_ids) == correct


def check_short(task: Task, text: str) -> bool:
    text = text[:MAX_ANSWER]
    for ans in task.answers:
        if ans.get("mode") == "regex":
            try:
                if re.fullmatch(ans["value"], text.strip(), re.IGNORECASE):
                    return True
            except re.error:
                continue
        elif normalize(text) == normalize(ans["value"]):
            return True
    return False
