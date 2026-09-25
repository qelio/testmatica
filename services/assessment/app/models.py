from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, SmallInteger, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from testmatica_common.ids import uuid7
from testmatica_common.messaging import messaging_tables

# Типы задач (ТЗ, раздел 10). Каждая задача — строго один тип.
CHOICE = "choice"  # выбор одного или нескольких вариантов — мгновенная автопроверка
SHORT = "short"  # слово, число, фраза — точное совпадение или шаблон (regex)
LONG = "long"  # развёрнутый ответ, возможен файл — проверяет педагог
CODE = "code"  # программа на Python, прогон тест-кейсов в песочнице
TYPES = (CHOICE, SHORT, LONG, CODE)
AUTO_TYPES = (CHOICE, SHORT, CODE)  # только такие можно добавлять в курсы библиотеки

# Статусы, как у курсов: приватная задача сразу доступна автору; в публичный банк — через модерацию.
PRIVATE, PENDING, PUBLISHED, REJECTED = "private", "pending", "published", "rejected"

# Статусы отправки решения.
CHECKING = "checking"
CORRECT = "correct"
INCORRECT = "incorrect"
ERROR = "error"  # сбой проверки (не вина ученика) — можно отправить снова
PENDING_REVIEW = "pending_review"
REVIEWED = "reviewed"


class Base(DeclarativeBase):
    pass


outbox, inbox = messaging_tables(Base.metadata)


class Person(Base):
    __tablename__ = "people"

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))


class RelLink(Base):
    """Привязки педагог–ученик: педагог видит решения своих учеников (в т. ч. код каждой попытки)."""

    __tablename__ = "rel_links"
    __table_args__ = (Index("ix_assessment_rel_links_student", "student_id"),)

    teacher_id: Mapped[UUID] = mapped_column(primary_key=True)
    student_id: Mapped[UUID] = mapped_column(primary_key=True)


class Topic(Base):
    """Общий рубрикатор банка задач: предмет → раздел → тема. Ведут модераторы.

    Предметы — справочник content (id и название копируются); раздел — тема без родителя.
    """

    __tablename__ = "topics"
    __table_args__ = (Index("ix_topics_tree", "subject_id", "parent_id", "position"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    subject_id: Mapped[UUID]
    subject_name: Mapped[str] = mapped_column(String(80))
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("topics.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Exam(Base):
    """Экзамен по предмету: ЕГЭ или ОГЭ (например, «ЕГЭ · Математика (профиль)»)."""

    __tablename__ = "exams"
    __table_args__ = (CheckConstraint("kind IN ('ege', 'oge')", name="kind_valid"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    kind: Mapped[str] = mapped_column(String(3))
    subject_id: Mapped[UUID]
    subject_name: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer, default=0)

    items: Mapped[list["ExamItem"]] = relationship(lazy="selectin", order_by="ExamItem.number", cascade="all, delete-orphan")


class ExamItem(Base):
    """Номер задания экзамена (ЕГЭ №8 «Производная») — тег для задач и занятий."""

    __tablename__ = "exam_items"
    __table_args__ = (UniqueConstraint("exam_id", "number", name="uq_exam_items_number"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    exam_id: Mapped[UUID] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(SmallInteger)
    title: Mapped[str] = mapped_column(String(200))


class ExamMark(Base):
    """Отметки педагога по заданиям экзамена для ученика или группы: «пройдено» и примечание."""

    __tablename__ = "exam_marks"
    __table_args__ = (
        CheckConstraint("target_type IN ('student', 'group')", name="target_type_valid"),
        UniqueConstraint("teacher_id", "target_type", "target_id", "item_id", name="uq_exam_marks_target_item"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    teacher_id: Mapped[UUID]
    target_type: Mapped[str] = mapped_column(String(10))
    target_id: Mapped[UUID]
    item_id: Mapped[UUID] = mapped_column(ForeignKey("exam_items.id", ondelete="CASCADE"))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("type IN ('choice', 'short', 'long', 'code')", name="type_valid"),
        CheckConstraint("status IN ('private', 'pending', 'published', 'rejected')", name="status_valid"),
        CheckConstraint("difficulty BETWEEN 1 AND 3", name="difficulty_valid"),
        CheckConstraint("file_mode IN ('none', 'optional', 'required')", name="file_mode_valid"),
        Index("ix_tasks_bank", "status", "subject_id", "type"),
        Index("ix_tasks_owner", "owner_id", "updated_at"),
        Index("ix_tasks_tags", "tags", postgresql_using="gin"),
        Index("ix_tasks_topic", "topic_id", "status"),
        Index("ix_tasks_exam_items", "exam_item_ids", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_id: Mapped[UUID]
    subject_id: Mapped[UUID | None]
    subject_name: Mapped[str | None] = mapped_column(String(80))
    # Место в рубрикаторе; предмет задачи берётся из темы.
    topic_id: Mapped[UUID | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"))
    # Задания ЕГЭ/ОГЭ, к которым относится задача (по ним считается прогресс ученика).
    exam_item_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid), default=list, server_default="{}")
    title: Mapped[str] = mapped_column(String(200))
    statement: Mapped[str] = mapped_column(Text)  # Markdown с формулами
    type: Mapped[str] = mapped_column(String(10))
    difficulty: Mapped[int] = mapped_column(SmallInteger, default=1)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")  # разбор решения
    theory_material_id: Mapped[UUID | None]  # теоркарточка из библиотеки
    # Развёрнутый ответ: можно ли / нужно ли прикрепить файл.
    file_mode: Mapped[str] = mapped_column(String(10), default="none")
    # Короткий ответ: [{"mode": "exact" | "regex", "value": "..."}]
    answers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Код:
    language: Mapped[str | None] = mapped_column(String(20))
    starter_code: Mapped[str] = mapped_column(Text, default="")
    time_limit_s: Mapped[float | None] = mapped_column(Float)
    memory_limit_mb: Mapped[int | None]

    status: Mapped[str] = mapped_column(String(10), default=PRIVATE)
    review_comment: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    based_on_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    options: Mapped[list["TaskOption"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="TaskOption.position"
    )
    tests: Mapped[list["TaskTest"]] = relationship(lazy="selectin", cascade="all, delete-orphan", order_by="TaskTest.position")


class TaskOption(Base):
    __tablename__ = "task_options"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)


class TaskTest(Base):
    """Тест-кейс задачи с кодом. Входные данные ученику не показываются."""

    __tablename__ = "task_tests"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    input: Mapped[str] = mapped_column(Text, default="")
    expected: Mapped[str] = mapped_column(Text, default="")


class CourseTask(Base):
    """Задачи, отправленные на модерацию вместе с курсом: публикуются вместе с ним."""

    __tablename__ = "course_tasks"

    course_id: Mapped[UUID] = mapped_column(primary_key=True)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)


class Submission(Base):
    """Отправка решения. Хранится каждая попытка целиком — в том числе код,
    поэтому педагог видит, каким кодом решалась задача и на чём падали прошлые попытки."""

    __tablename__ = "submissions"
    __table_args__ = (
        CheckConstraint("context_type IN ('practice', 'assignment')", name="context_valid"),
        CheckConstraint(
            "status IN ('checking', 'correct', 'incorrect', 'error', 'pending_review', 'reviewed')", name="status_valid"
        ),
        Index("ix_submissions_student_task", "student_id", "task_id", "created_at"),
        Index("ix_submissions_context", "context_type", "context_id", "student_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    student_id: Mapped[UUID]
    # practice — задача в модуле библиотеки (context_id = id материала); assignment — тест/ДЗ.
    context_type: Mapped[str] = mapped_column(String(12))
    context_id: Mapped[UUID]
    # {"option_ids": [...]} | {"text": "..."} | {"code": "..."}
    answer: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # [{"id", "filename", "mime", "size"}] — файлы из media (развёрнутый ответ)
    files: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16))
    score: Mapped[float | None] = mapped_column(Float)  # 0…1
    # Для кода: номер первого упавшего теста и его вид — это видит ученик.
    failed_case: Mapped[int | None]
    failure: Mapped[str | None] = mapped_column(String(20))
    # Полный протокол прогона (выводы, ошибки) — только для педагога.
    run_log: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    teacher_comment: Mapped[str | None] = mapped_column(Text)
    reviewer_id: Mapped[UUID | None]
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------- тесты и ДЗ ----------

HOMEWORK, LIVE = "homework", "live"  # домашнее задание / активный тест на уроке
IN_PROGRESS, SUBMITTED = "in_progress", "submitted"


class Test(Base):
    """Тест — набор задач из банка с настройками прохождения. Выдаётся как ДЗ или запускается на уроке."""

    __tablename__ = "tests"
    __table_args__ = (
        CheckConstraint("order_mode IN ('fixed', 'random')", name="order_mode_valid"),
        CheckConstraint("time_mode IN ('none', 'total', 'per_task')", name="time_mode_valid"),
        Index("ix_tests_owner", "owner_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    owner_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    order_mode: Mapped[str] = mapped_column(String(6), default="fixed")  # порядок заданий
    shuffle_options: Mapped[bool] = mapped_column(Boolean, default=False)  # варианты ответа у каждого свои
    time_mode: Mapped[str] = mapped_column(String(8), default="none")  # таймер на весь тест или на каждое задание
    time_limit_s: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    items: Mapped[list["TestItem"]] = relationship(lazy="selectin", cascade="all, delete-orphan", order_by="TestItem.position")


class TestItem(Base):
    __tablename__ = "test_items"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    test_id: Mapped[UUID] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(SmallInteger, default=1)


class Assignment(Base):
    """Выдача теста группе или ученику. Состав и настройки копируются: правка теста не меняет выданное."""

    __tablename__ = "assignments"
    __table_args__ = (
        CheckConstraint("kind IN ('homework', 'live')", name="kind_valid"),
        CheckConstraint("target_type IN ('student', 'group')", name="target_type_valid"),
        Index("ix_assignments_teacher", "teacher_id", "created_at"),
        Index("ix_assignments_lesson", "lesson_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    test_id: Mapped[UUID] = mapped_column(ForeignKey("tests.id", ondelete="RESTRICT"))
    teacher_id: Mapped[UUID]
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(8))
    target_type: Mapped[str] = mapped_column(String(10))
    target_id: Mapped[UUID]
    target_title: Mapped[str] = mapped_column(String(200))
    lesson_id: Mapped[UUID | None]  # урок в расписании: колонка журнала для автооценки
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # {order_mode, shuffle_options, time_mode, time_limit_s}
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # [{task_id, points}] — в порядке теста
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    grade_to_journal: Mapped[bool] = mapped_column(Boolean, default=False)
    grade_type_id: Mapped[UUID | None]
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # тест на уроке завершён
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    students: Mapped[list["AssignmentStudent"]] = relationship(lazy="selectin", cascade="all, delete-orphan")


class AssignmentStudent(Base):
    """Кому выдано. allowed_attempts растёт при переназначении — повторная сдача только так (ТЗ)."""

    __tablename__ = "assignment_students"
    __table_args__ = (Index("ix_assignment_students_student", "student_id"),)

    assignment_id: Mapped[UUID] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), primary_key=True)
    student_id: Mapped[UUID] = mapped_column(primary_key=True)
    allowed_attempts: Mapped[int] = mapped_column(SmallInteger, default=1)
    # Личный дедлайн — при переназначении после общего дедлайна.
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Attempt(Base):
    """Попытка прохождения: свой порядок заданий и вариантов, таймер, черновики до сдачи, итог после."""

    __tablename__ = "attempts"
    __table_args__ = (
        CheckConstraint("status IN ('in_progress', 'submitted')", name="status_valid"),
        UniqueConstraint("assignment_id", "student_id", "number", name="uq_attempts_number"),
        Index("ix_attempts_open", "status", "ends_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    assignment_id: Mapped[UUID] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"))
    student_id: Mapped[UUID]
    number: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(12), default=IN_PROGRESS)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # таймер на весь тест
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auto_submitted: Mapped[bool] = mapped_column(Boolean, default=False)  # сдано по истечении времени
    task_order: Mapped[list[str]] = mapped_column(JSONB)
    option_orders: Mapped[dict[str, list[str]]] = mapped_column(JSONB, default=dict)
    # Таймер на каждое задание: текущее задание и когда оно открыто. Вернуться назад нельзя.
    current_index: Mapped[int] = mapped_column(SmallInteger, default=0)
    current_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[float | None] = mapped_column(Float)
    max_score: Mapped[float] = mapped_column(Float, default=0)
    percent: Mapped[float | None] = mapped_column(Float)
    grade: Mapped[int | None] = mapped_column(SmallInteger)
    checked: Mapped[bool] = mapped_column(Boolean, default=False)  # все ответы проверены (код, развёрнутые)


class AttemptAnswer(Base):
    """Черновик ответа в попытке — меняется до сдачи; при сдаче превращается в отправку (submissions)."""

    __tablename__ = "attempt_answers"

    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("attempts.id", ondelete="CASCADE"), primary_key=True)
    task_id: Mapped[UUID] = mapped_column(primary_key=True)
    answer: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    files: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
