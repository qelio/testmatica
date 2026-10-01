from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

AttendanceStatus = Literal["present", "absent", "late", "sick"]


def _required_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Комментарий обязателен")
    return value


class GradeTypeOut(BaseModel):
    id: UUID
    name: str
    position: int
    is_active: bool


class GradeTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    position: int = 0

    _name = field_validator("name")(_required_text)


class GradeTypeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    position: int | None = None
    is_active: bool | None = None


class GradeCreate(BaseModel):
    student_id: UUID
    value: int = Field(ge=1, le=5)
    grade_type_id: UUID
    comment: str = Field(max_length=1000)

    _comment = field_validator("comment")(_required_text)


class GradeUpdate(BaseModel):
    value: int | None = Field(None, ge=1, le=5)
    grade_type_id: UUID | None = None
    comment: str | None = Field(None, max_length=1000)

    @field_validator("comment")
    @classmethod
    def _comment(cls, value: str | None) -> str | None:
        return None if value is None else _required_text(value)


class GradeOut(BaseModel):
    id: UUID
    lesson_id: UUID | None = Field(description="Урок; пусто — оценка за работу (колонка work_id)")
    work_id: UUID | None = Field(None, description="Работа из assessment, за которую оценка")
    title: str | None = Field(None, description="Название работы")
    student_id: UUID
    value: int
    grade_type_id: UUID
    grade_type: str
    comment: str
    source: str
    lesson_starts_at: datetime
    created_at: datetime


class AttendanceSet(BaseModel):
    status: AttendanceStatus | None = Field(description="null — снять отметку")


class AttendanceOut(BaseModel):
    lesson_id: UUID
    student_id: UUID
    status: AttendanceStatus


class Stats(BaseModel):
    average: float | None = Field(description="Средний балл, null — оценок нет")
    grades_count: int
    present: int
    late: int
    absent: int
    sick: int
    attendance_rate: float | None = Field(description="Доля посещённых (присутствовал или опоздал) среди отмеченных")


class JournalLesson(BaseModel):
    id: UUID
    starts_at: datetime
    subject: str | None
    topic: str | None
    started: bool
    ktp: list[str] = Field(default_factory=list, description="Темы уроков КТП, привязанных к занятию")


class JournalWork(BaseModel):
    """Колонка журнала для оценок за тест или ДЗ без привязки к уроку."""

    id: UUID = Field(description="id выданной работы в assessment")
    title: str
    at: datetime = Field(description="Когда работа назначена")


class JournalStudent(BaseModel):
    id: UUID
    full_name: str
    current: bool = Field(description="Сейчас в группе (ушедшие показываются, если у них есть записи)")
    stats: Stats


class Journal(BaseModel):
    title: str
    lessons: list[JournalLesson]
    works: list[JournalWork] = Field(default_factory=list)
    students: list[JournalStudent]
    grades: list[GradeOut]
    attendance: list[AttendanceOut]
    stats: Stats


class SubjectGrades(BaseModel):
    subject: str
    teacher_names: list[str]
    stats: Stats
    grades: list[GradeOut]


class MyGrades(BaseModel):
    subjects: list[SubjectGrades]
    stats: Stats


# ---------- КТП ----------


def _squash(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


class PlanItem(BaseModel):
    """Материал «к уроку» или «на дом»: модуль библиотеки, тест, ссылка или просто заметка."""

    kind: Literal["module", "test", "link", "note"]
    ref_id: UUID | None = None
    title: str = Field(min_length=1, max_length=300)
    url: str | None = Field(None, max_length=1000)

    @model_validator(mode="after")
    def _check(self) -> "PlanItem":
        if self.kind in ("module", "test") and self.ref_id is None:
            raise ValueError("Не указан модуль или тест")
        if self.kind == "link" and not (self.url or "").startswith(("http://", "https://")):
            raise ValueError("Ссылка должна начинаться с http:// или https://")
        return self


class LessonIn(BaseModel):
    topic: str = Field(min_length=1, max_length=300)
    goals: str = Field("", max_length=5000)
    class_items: list[PlanItem] = Field(default_factory=list, max_length=20)
    home_items: list[PlanItem] = Field(default_factory=list, max_length=20)
    exam_item_ids: list[UUID] = Field(default_factory=list, max_length=10)

    _topic = field_validator("topic")(_squash)


class TemplateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    subject: str | None = Field(None, max_length=80)
    level: str | None = Field(None, max_length=40)
    description: str = Field("", max_length=5000)
    lessons: list[LessonIn] = Field(default_factory=list, max_length=300)

    _title = field_validator("title", "subject", "level")(_squash)


class TemplateLessonOut(LessonIn):
    id: UUID


class TemplateSummary(BaseModel):
    id: UUID
    title: str
    subject: str | None
    level: str | None
    status: str
    owner_id: UUID
    author_name: str
    lessons_count: int
    updated_at: datetime


class TemplateOut(TemplateSummary):
    description: str
    review_comment: str | None
    based_on_id: UUID | None
    can_edit: bool
    lessons: list[TemplateLessonOut]


class PlanCreate(BaseModel):
    target_type: Literal["student", "group"]
    target_id: UUID
    title: str | None = Field(None, max_length=200)
    subject: str | None = Field(None, max_length=80)
    template_id: UUID | None = Field(None, description="Взять уроки из шаблона; без него — пустой план (с нуля или постепенно)")
    start_date: date | None = None
    distribute: bool = Field(True, description="Сразу разложить уроки по занятиям расписания с даты начала")

    _title = field_validator("title", "subject")(_squash)


class PlanUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    subject: str | None = Field(None, max_length=80)
    start_date: date | None = None

    _title = field_validator("title", "subject")(_squash)


class PlanLessonUpdate(BaseModel):
    topic: str | None = Field(None, min_length=1, max_length=300)
    goals: str | None = Field(None, max_length=5000)
    class_items: list[PlanItem] | None = Field(None, max_length=20)
    home_items: list[PlanItem] | None = Field(None, max_length=20)
    exam_item_ids: list[UUID] | None = Field(None, max_length=10)
    planned_date: date | None = None
    schedule_lesson_id: UUID | None = None
    done: bool | None = None

    _topic = field_validator("topic")(_squash)


class PlanLessonOut(LessonIn):
    id: UUID
    position: int
    planned_date: date | None
    schedule_lesson_id: UUID | None
    done: bool


class Slot(BaseModel):
    """Занятие цели в расписании — куда можно поставить урок КТП."""

    id: UUID
    starts_at: datetime
    topic: str | None


class PlanSummary(BaseModel):
    id: UUID
    title: str
    subject: str | None
    target_type: str
    target_id: UUID
    target_title: str
    lessons_count: int
    done_count: int
    next_topic: str | None
    next_date: date | None
    updated_at: datetime


class PlanOut(BaseModel):
    id: UUID
    title: str
    subject: str | None
    target_type: str
    target_id: UUID
    target_title: str
    template_id: UUID | None
    start_date: date | None
    lessons: list[PlanLessonOut]
    slots: list[Slot] = Field(description="Занятия цели от даты начала — для привязки уроков")
    updated_at: datetime


class DistributeIn(BaseModel):
    from_date: date | None = Field(None, description="С какого дня раскладывать; по умолчанию — дата начала плана или сегодня")
    tz: str = Field("Europe/Moscow", max_length=64)


class DistributeOut(BaseModel):
    placed: int
    left: int = Field(description="Урокам не хватило занятий в расписании")


class LessonKtp(BaseModel):
    plan_id: UUID
    plan_title: str
    lesson: PlanLessonOut


# ---------- расширенная аналитика ----------


class TrendPoint(BaseModel):
    week: date = Field(description="Понедельник недели")
    average: float | None
    attendance_rate: float | None = None


class HeatDay(BaseModel):
    day: date
    marked: int = Field(description="Сколько отметок посещаемости")
    missed: int = Field(description="Пропуски: отсутствовал или болел")
    rate: float = Field(description="Доля пропусков")


class StudentLine(BaseModel):
    id: UUID
    full_name: str
    current: bool
    stats: Stats
    delta: float | None = Field(None, description="Средний балл минус средний по классу (расширенная)")
    trend: list[TrendPoint] | None = None


class GroupReport(BaseModel):
    title: str
    subject: str | None
    period_from: date
    period_to: date
    extended: bool = Field(description="Тариф «Базовый»: динамика, сравнение, тепловая карта, выгрузка")
    stats: Stats
    students: list[StudentLine]
    distribution: dict[int, int] | None = Field(None, description="Сколько оценок 1–5")
    trend: list[TrendPoint] | None = None
    heatmap: list[HeatDay] | None = None


class SubjectLine(BaseModel):
    subject: str
    stats: Stats
    class_average: float | None = Field(None, description="Средний по группам ученика по этому предмету")


class GradePoint(BaseModel):
    at: datetime
    value: int
    subject: str | None
    grade_type: str
    comment: str


class StudentReport(BaseModel):
    full_name: str
    period_from: date
    period_to: date
    extended: bool
    stats: Stats
    subjects: list[SubjectLine]
    grades: list[GradePoint] | None = None
    trend: list[TrendPoint] | None = None


class SummaryLine(BaseModel):
    group_id: UUID | None = Field(description="None — индивидуальные занятия")
    title: str
    students: int
    stats: Stats
    below_three: int = Field(description="Учеников со средним ниже 3")


class Summary(BaseModel):
    period_from: date
    period_to: date
    rows: list[SummaryLine]
    total: Stats
