import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

TaskType = Literal["choice", "short", "long", "code"]


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


class OptionIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    is_correct: bool = False


class ShortAnswerIn(BaseModel):
    mode: Literal["exact", "regex"] = "exact"
    value: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _regex_ok(self) -> "ShortAnswerIn":
        if self.mode == "regex":
            try:
                re.compile(self.value)
            except re.error as e:
                raise ValueError(f"Неверный шаблон: {e}") from None
        return self


class TestIn(BaseModel):
    input: str = Field("", max_length=100_000)
    expected: str = Field(max_length=100_000)


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1, max_length=50_000)
    type: TaskType
    subject_id: UUID | None = None
    subject_name: str | None = Field(None, max_length=80)
    topic_id: UUID | None = Field(None, description="Тема рубрикатора; предмет задачи берётся из неё")
    exam_item_ids: list[UUID] = Field(default_factory=list, max_length=10, description="Задания ЕГЭ/ОГЭ")
    difficulty: int = Field(1, ge=1, le=3)
    tags: list[str] = Field(default_factory=list, max_length=10)
    explanation: str = Field("", max_length=50_000)
    theory_material_id: UUID | None = None
    file_mode: Literal["none", "optional", "required"] = "none"
    options: list[OptionIn] = Field(default_factory=list, max_length=12)
    answers: list[ShortAnswerIn] = Field(default_factory=list, max_length=20)
    starter_code: str = Field("", max_length=20_000)
    time_limit_s: float = Field(2, gt=0, le=10)
    memory_limit_mb: int = Field(128, ge=32, le=512)
    tests: list[TestIn] = Field(default_factory=list, max_length=50)

    _title = field_validator("title")(_clean)

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: list[str]) -> list[str]:
        return sorted({t.strip().lower()[:40] for t in value if t.strip()})

    @model_validator(mode="after")
    def _by_type(self) -> "TaskIn":
        if self.type == "choice":
            if len(self.options) < 2:
                raise ValueError("Нужно хотя бы два варианта ответа")
            if not any(o.is_correct for o in self.options):
                raise ValueError("Отметьте правильный вариант")
        if self.type == "short" and not self.answers:
            raise ValueError("Укажите правильный ответ")
        if self.type == "code" and not self.tests:
            raise ValueError("Добавьте хотя бы один тест-кейс")
        if self.type != "long":
            self.file_mode = "none"
        return self


class TopicIn(BaseModel):
    subject_id: UUID | None = Field(None, description="Для раздела; тема наследует предмет раздела")
    subject_name: str | None = Field(None, max_length=80)
    parent_id: UUID | None = None
    title: str = Field(min_length=1, max_length=120)

    _title = field_validator("title")(_clean)


class TopicUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=120)
    position: int | None = Field(None, ge=0)

    _title = field_validator("title")(_clean)


class TopicOut(BaseModel):
    id: UUID
    subject_id: UUID
    subject_name: str
    parent_id: UUID | None
    title: str
    position: int
    count: int = Field(0, description="Задач прямо в этом узле (для выбранного scope)")


class TopicMove(BaseModel):
    topic_id: UUID


class OptionOut(BaseModel):
    id: UUID
    text: str
    is_correct: bool | None = Field(None, description="Только для автора и педагогов")


class ExamLabel(BaseModel):
    id: UUID
    label: str = Field(description="«ЕГЭ №8» — для чипов задач и занятий")
    title: str


class TaskSummary(BaseModel):
    id: UUID
    title: str
    type: str
    difficulty: int
    subject_id: UUID | None
    subject_name: str | None
    topic_id: UUID | None
    topic_path: list[str] = Field(description="Раздел и тема: ['Дроби', 'Сложение и вычитание дробей']")
    exam_items: list[ExamLabel] = Field(default_factory=list)
    tags: list[str]
    status: str
    owner_id: UUID
    author_name: str
    updated_at: datetime


class TaskOut(TaskSummary):
    """Полная задача: для автора и педагогов — с ответами и тест-кейсами."""

    statement: str
    explanation: str
    theory_material_id: UUID | None
    file_mode: str
    options: list[OptionOut]
    answers: list[dict[str, Any]] | None
    starter_code: str
    time_limit_s: float | None
    memory_limit_mb: int | None
    tests: list[TestIn] | None
    review_comment: str | None
    can_edit: bool
    multiple: bool = Field(description="Выбор ответа: несколько правильных вариантов")


class TaskPage(BaseModel):
    items: list[TaskSummary]
    total: int


# ---------- решение ----------


class AnswerIn(BaseModel):
    option_ids: list[UUID] | None = None
    text: str | None = Field(None, max_length=20_000)
    code: str | None = Field(None, max_length=100_000)


class SubmissionIn(BaseModel):
    context_type: Literal["practice", "assignment"] = "practice"
    context_id: UUID
    answer: AnswerIn
    file_ids: list[UUID] = Field(default_factory=list, max_length=5)


class FileRef(BaseModel):
    id: UUID
    filename: str
    mime: str
    size: int
    url: str | None = None


class SubmissionOut(BaseModel):
    id: UUID
    task_id: UUID
    student_id: UUID
    context_type: str
    context_id: UUID
    answer: dict[str, Any]
    files: list[FileRef]
    status: str
    score: float | None
    failed_case: int | None
    failure: str | None
    teacher_comment: str | None
    created_at: datetime
    checked_at: datetime | None
    run_log: list[dict[str, Any]] | None = Field(None, description="Протокол прогона — только педагогу")
    task_title: str | None = Field(None, description="Название задачи — в истории ученика для педагога")
    task_type: str | None = None


class SolveView(BaseModel):
    """Задача глазами ученика: без правильных ответов и тест-кейсов."""

    task: TaskOut
    submissions: list[SubmissionOut]
    solved: bool
    explanation: str | None = Field(description="Разбор — после верного ответа или нескольких попыток")


class ReviewIn(BaseModel):
    score: float = Field(ge=0, le=1)
    comment: str = Field(min_length=1, max_length=5000)


# ---------- ЕГЭ / ОГЭ ----------


class ExamItemOut(BaseModel):
    id: UUID
    number: int
    title: str


class ExamOut(BaseModel):
    id: UUID
    kind: Literal["ege", "oge"]
    subject_id: UUID
    subject_name: str
    title: str
    items: list[ExamItemOut]


class ExamIn(BaseModel):
    kind: Literal["ege", "oge"]
    subject_id: UUID
    subject_name: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)

    _title = field_validator("title")(_clean)


class ExamItemIn(BaseModel):
    number: int = Field(ge=1, le=99)
    title: str = Field(min_length=1, max_length=200)

    _title = field_validator("title")(_clean)


class ExamItemUpdate(BaseModel):
    number: int | None = Field(None, ge=1, le=99)
    title: str | None = Field(None, min_length=1, max_length=200)

    _title = field_validator("title")(_clean)


class Progress(BaseModel):
    """Решения по заданию экзамена: задачи (разные) и попытки."""

    attempted: int = Field(0, description="Сколько разных задач пробовал решить")
    solved: int = Field(0, description="Сколько из них решил верно")
    attempts: int = 0
    correct_attempts: int = 0
    last_at: datetime | None = None


class StudentProgress(Progress):
    student_id: UUID


class BoardRow(BaseModel):
    item_id: UUID
    number: int
    title: str
    done: bool
    done_at: datetime | None
    note: str | None = Field(description="Примечание педагога — ученику не показывается")
    progress: Progress
    by_student: list[StudentProgress] = Field(default_factory=list, description="Для группы — по каждому ученику")
    tasks_in_bank: int = Field(description="Опубликованных задач в банке по этому заданию")


class BoardPerson(BaseModel):
    id: UUID
    full_name: str


class ExamBoard(BaseModel):
    exam: ExamOut
    target_type: Literal["student", "group"]
    target_id: UUID
    can_edit: bool
    students: list[BoardPerson]
    rows: list[BoardRow]


class MarkIn(BaseModel):
    target_type: Literal["student", "group"]
    target_id: UUID
    item_id: UUID
    done: bool = False
    note: str = Field("", max_length=2000)


class ItemTaskProgress(BaseModel):
    task_id: UUID
    title: str
    type: str
    attempts: int
    solved: bool
    last_status: str
    last_at: datetime
