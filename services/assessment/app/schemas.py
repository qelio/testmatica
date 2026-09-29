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
    theory: bool = Field(description="Материал: выдали теорию, как решать")
    practice: bool = Field(description="Практика: ученики решали сами, не на оценку")
    control: bool = Field(description="Контроль: проверили знания")
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
    # Не переданное поле не меняется: разные галочки сохраняются независимо.
    theory: bool | None = None
    practice: bool | None = None
    control: bool | None = None
    done: bool | None = None
    note: str | None = Field(None, max_length=2000)


class ItemTaskProgress(BaseModel):
    task_id: UUID
    title: str
    type: str
    attempts: int
    solved: bool
    last_status: str
    last_at: datetime


# ---------- тесты, ДЗ, попытки ----------
# «Quiz» в названиях схем — чтобы не путать с тест-кейсами задач с кодом (TestIn).


class QuizItemIn(BaseModel):
    task_id: UUID
    points: int = Field(1, ge=1, le=100)


class QuizIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field("", max_length=5000)
    order_mode: Literal["fixed", "random"] = "fixed"
    shuffle_options: bool = False
    time_mode: Literal["none", "total", "per_task"] = "none"
    time_limit_s: int | None = Field(None, ge=10, le=6 * 3600, description="Секунды: на весь тест или на каждое задание")
    items: list[QuizItemIn] = Field(default_factory=list, max_length=100)

    _title = field_validator("title")(_clean)

    @model_validator(mode="after")
    def _timer(self) -> "QuizIn":
        if self.time_mode == "none":
            self.time_limit_s = None
        elif self.time_limit_s is None:
            raise ValueError("Укажите ограничение времени")
        if len({i.task_id for i in self.items}) != len(self.items):
            raise ValueError("Задача добавлена в тест дважды")
        return self


class QuizItemOut(BaseModel):
    task_id: UUID
    points: int
    task: TaskSummary


class QuizOut(BaseModel):
    id: UUID
    title: str
    description: str
    order_mode: str
    shuffle_options: bool
    time_mode: str
    time_limit_s: int | None
    items: list[QuizItemOut]
    max_score: int
    assignments_count: int
    updated_at: datetime


class QuizSummary(BaseModel):
    id: UUID
    title: str
    tasks_count: int
    max_score: int
    time_mode: str
    time_limit_s: int | None
    assignments_count: int
    updated_at: datetime


class AssignIn(BaseModel):
    kind: Literal["test", "homework", "live"] = Field(
        "test", description="Просто тест / тест на дом (к уроку) / тест на уроке (к уроку, прогресс в реальном времени)"
    )
    title: str | None = Field(None, max_length=200, description="Название назначения для учеников; по умолчанию — название теста")
    target_type: Literal["student", "group"]
    target_id: UUID
    lesson_id: UUID | None = Field(None, description="Урок в расписании — для ДЗ и теста на уроке; нужен и для оценки в журнал")
    opens_at: datetime | None = Field(None, description="Когда откроется; по умолчанию — сразу")
    deadline: datetime | None = Field(None, description="Когда закроется; по умолчанию — не закрывается")
    max_attempts: int | None = Field(1, ge=1, le=50, description="Сколько попыток; null — без ограничений (засчитывается лучшая)")
    grade_to_journal: bool = False
    grade_type_id: UUID | None = None
    proctoring: bool = Field(False, description="Прокторинг — тариф «Базовый»; ученик даёт согласие при старте")

    _title = field_validator("title")(_clean)

    @model_validator(mode="after")
    def _rules(self) -> "AssignIn":
        for value in (self.opens_at, self.deadline):
            if value is not None and value.tzinfo is None:
                raise ValueError("Время нужно передавать с часовым поясом")
        if self.opens_at and self.deadline and self.deadline <= self.opens_at:
            raise ValueError("Тест должен закрываться позже, чем откроется")
        if self.kind in ("homework", "live") and self.lesson_id is None:
            raise ValueError("Выберите урок, к которому относится тест")
        if self.kind == "test":
            self.lesson_id = None
        if self.grade_to_journal and (self.lesson_id is None or self.grade_type_id is None):
            raise ValueError("Для оценки в журнал выберите урок и тип оценки")
        return self


class AttemptBrief(BaseModel):
    id: UUID
    number: int
    status: str
    started_at: datetime
    submitted_at: datetime | None
    auto_submitted: bool
    answered: int = Field(description="Сколько заданий с ответом (для прогресса на уроке)")
    total: int
    score: float | None
    max_score: float
    percent: float | None
    grade: int | None
    checked: bool


class AssignmentStudentOut(BaseModel):
    student_id: UUID
    full_name: str
    allowed_attempts: int
    attempts: list[AttemptBrief]
    proctor_alerts: int = Field(0, description="Прокторинг: сколько раз уходил со вкладки или прекращал показ экрана")


class AssignmentOut(BaseModel):
    id: UUID
    test_id: UUID
    title: str = Field(description="Название назначения — его видят ученики")
    test_title: str = Field(description="Название теста на момент назначения — для педагога")
    description: str
    kind: str
    proctoring: bool = False
    target_type: str
    target_id: UUID
    target_title: str
    teacher_id: UUID
    teacher_name: str
    lesson_id: UUID | None
    opens_at: datetime | None
    deadline: datetime | None
    not_open_yet: bool
    overdue: bool
    closed: bool
    max_attempts: int | None = Field(description="Попыток на ученика; null — без ограничений")
    settings: dict[str, Any]
    tasks_count: int
    max_score: int
    grade_to_journal: bool
    grade_type_id: UUID | None
    created_at: datetime
    # Педагогу — сводка по ученикам, ученику — только его строка.
    students: list[AssignmentStudentOut]
    can_start: bool = Field(False, description="Ученику: можно начать новую попытку")
    attempts_left: int | None = Field(None, description="Ученику: сколько попыток осталось; null — без ограничений")


class AttemptTask(BaseModel):
    """Задание в попытке глазами ученика; после сдачи — с результатом."""

    task: TaskOut
    points: int
    answer: dict[str, Any] | None
    files: list[FileRef]
    locked: bool = Field(description="Таймер на задание: время вышло или задание пройдено")
    result: SubmissionOut | None = None
    earned: float | None = None


class AttemptOut(BaseModel):
    id: UUID
    assignment_id: UUID
    title: str
    student_id: UUID
    number: int
    status: str
    settings: dict[str, Any]
    started_at: datetime
    ends_at: datetime | None
    current_index: int
    current_ends_at: datetime | None
    submitted_at: datetime | None
    auto_submitted: bool
    score: float | None
    max_score: float
    percent: float | None
    grade: int | None
    checked: bool
    server_time: datetime = Field(description="Для точного таймера на клиенте")
    proctoring: bool = False
    tasks: list[AttemptTask]


class DraftIn(BaseModel):
    answer: AnswerIn
    file_ids: list[UUID] = Field(default_factory=list, max_length=5)


class StartIn(BaseModel):
    consent: bool = Field(False, description="Согласие на прокторинг — обязательно, если он включён")


class ProctorEventIn(BaseModel):
    kind: Literal["screen_share_started", "screen_share_stopped", "tab_hidden", "tab_visible", "focus_lost", "focus_back",
                  "camera_requested", "camera_on", "camera_off"]


class ProctorEventOut(BaseModel):
    kind: str
    at: datetime


class ProctorStudent(BaseModel):
    id: UUID
    full_name: str
    attempt_id: UUID | None = Field(description="Идущая попытка")


class ProctorAccess(BaseModel):
    """Для video: кто этот пользователь в прокторинге назначения."""

    role: Literal["teacher", "student"]
    assignment_id: UUID
    teacher_id: UUID
    title: str
    closed: bool
    attempt_id: UUID | None = Field(None, description="Ученику — идущая попытка (без неё к экрану не подключиться)")
    students: list[ProctorStudent] = Field(default_factory=list, description="Педагогу — ученики назначения")
