"""Банк задач: поиск, создание, редактирование, публикация."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_MODERATOR, ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import access, views
from ..deps import auth, db, outbox
from ..models import AUTO_TYPES, CODE, PENDING, PRIVATE, PUBLISHED, REJECTED, REMOVED, ExamItem, Task, TaskOption, TaskTest, Topic
from ..schemas import TaskIn, TaskOut, TaskPage, TopicMove

router = APIRouter(prefix="/tasks", tags=["tasks"])
author = auth.require(ROLE_TEACHER, ROLE_MODERATOR)


@router.get("", response_model=TaskPage)
async def search(
    scope: str = Query("public", pattern="^(public|mine)$"),
    subject_id: UUID | None = None,
    topic_id: UUID | None = Query(None, description="Раздел или тема; для раздела — вместе с его темами"),
    no_topic: bool = Query(False, description="Задачи без темы"),
    exam_item_id: UUID | None = Query(None, description="Задание ЕГЭ/ОГЭ"),
    type: str | None = Query(None, pattern="^(choice|short|long|code)$"),
    auto_only: bool = Query(False, description="Только с автопроверкой — для курсов библиотеки"),
    difficulty: int | None = Query(None, ge=1, le=3),
    tag: str | None = Query(None, max_length=40),
    q: str | None = Query(None, max_length=100),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(author),
    session: AsyncSession = Depends(db.session),
) -> TaskPage:
    """Публичный банк (опубликованные задачи всех авторов) или «мои задачи» в любом статусе."""
    query = select(Task).where(Task.owner_id == principal.user_id) if scope == "mine" else select(Task).where(Task.status == PUBLISHED)
    if subject_id:
        query = query.where(Task.subject_id == subject_id)
    if topic_id:
        children = select(Topic.id).where(Topic.parent_id == topic_id)
        query = query.where(or_(Task.topic_id == topic_id, Task.topic_id.in_(children)))
    if no_topic:
        query = query.where(Task.topic_id.is_(None))
    if exam_item_id:
        query = query.where(Task.exam_item_ids.contains([exam_item_id]))
    if type:
        query = query.where(Task.type == type)
    if auto_only:
        query = query.where(Task.type.in_(AUTO_TYPES))
    if difficulty:
        query = query.where(Task.difficulty == difficulty)
    if tag:
        query = query.where(Task.tags.contains([tag.strip().lower()]))
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Task.title.ilike(like), Task.statement.ilike(like)))
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await session.execute(query.order_by(Task.updated_at.desc()).limit(limit).offset(offset))).scalars().all()
    return TaskPage(items=await views.summaries(session, rows), total=total or 0)


async def _set_topic(session: AsyncSession, task: Task, topic_id: UUID | None) -> None:
    """Тема задаёт и предмет задачи — так задача всегда лежит в своём разделе рубрикатора."""
    task.topic_id = topic_id
    if topic_id is None:
        return
    topic = await session.get(Topic, topic_id)
    if topic is None:
        raise ApiError(422, "topic_not_found", "Тема не найдена — выберите другую")
    task.subject_id, task.subject_name = topic.subject_id, topic.subject_name


async def _apply(session: AsyncSession, task: Task, body: TaskIn) -> None:
    for field in ("title", "statement", "type", "subject_id", "subject_name", "difficulty", "tags", "explanation",
                  "theory_material_id", "file_mode", "starter_code"):
        setattr(task, field, getattr(body, field))
    await _set_topic(session, task, body.topic_id)
    item_ids = list(dict.fromkeys(body.exam_item_ids))
    if item_ids:
        known = set((await session.execute(select(ExamItem.id).where(ExamItem.id.in_(item_ids)))).scalars())
        if len(known) != len(item_ids):
            raise ApiError(422, "exam_item_not_found", "Задание ЕГЭ/ОГЭ не найдено — обновите страницу")
    task.exam_item_ids = item_ids
    task.answers = [a.model_dump() for a in body.answers] if body.type == "short" else []
    task.options = [TaskOption(text=o.text, is_correct=o.is_correct, position=i) for i, o in enumerate(body.options)] if body.type == "choice" else []
    task.tests = [TaskTest(input=c.input, expected=c.expected, position=i) for i, c in enumerate(body.tests)] if body.type == CODE else []
    if body.type == CODE:
        task.language, task.time_limit_s, task.memory_limit_mb = "python", body.time_limit_s, body.memory_limit_mb
    else:
        task.language = task.time_limit_s = task.memory_limit_mb = None


@router.post("", response_model=TaskOut, status_code=201)
async def create(body: TaskIn, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> TaskOut:
    task = Task(owner_id=principal.user_id, status=PRIVATE)
    await _apply(session, task, body)
    session.add(task)
    await session.flush()
    await outbox.event(session, "assessment.task.created", {"task_id": str(task.id), "type": task.type}, actor_id=principal.user_id)
    await session.commit()
    return await views.full(session, task, principal)


@router.get("/{task_id}", response_model=TaskOut)
async def get(
    task_id: UUID, principal: Principal | None = Depends(auth.optional), session: AsyncSession = Depends(db.session)
) -> TaskOut:
    """Карточка задачи. Ответы и тест-кейсы видят только автор, модераторы и педагоги (для опубликованных)."""
    return await views.full(session, await access.viewable(session, task_id, principal), principal)


@router.put("/{task_id}", response_model=TaskOut)
async def update(
    task_id: UUID, body: TaskIn, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)
) -> TaskOut:
    task = await access.editable(session, task_id, principal)
    await _apply(session, task, body)
    task.updated_at = datetime.now(UTC)
    await session.commit()
    return await views.full(session, task, principal)


@router.delete("/{task_id}", status_code=204)
async def delete(task_id: UUID, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> None:
    task = await access.editable(session, task_id, principal)
    await outbox.event(session, "assessment.task.deleted", {"task_id": str(task.id)}, actor_id=principal.user_id)
    await session.delete(task)
    await session.commit()


@router.post("/{task_id}/copy", response_model=TaskOut, status_code=201)
async def copy(task_id: UUID, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> TaskOut:
    """Взять задачу из банка за основу: приватная копия со всеми ответами и тестами."""
    source = await access.viewable(session, task_id, principal)
    if source.status == REMOVED and not access.is_staff(principal):
        raise ApiError(404, "task_not_found", "Задача не найдена")
    if not access.can_see_key(source, principal):
        raise ApiError(403, "forbidden", "Эту задачу нельзя скопировать")
    body = TaskIn(
        title=source.title, statement=source.statement, type=source.type, subject_id=source.subject_id,
        subject_name=source.subject_name, topic_id=source.topic_id, exam_item_ids=source.exam_item_ids, difficulty=source.difficulty, tags=source.tags, explanation=source.explanation,
        theory_material_id=source.theory_material_id, file_mode=source.file_mode,
        options=[{"text": o.text, "is_correct": o.is_correct} for o in source.options],
        answers=source.answers, starter_code=source.starter_code, time_limit_s=source.time_limit_s or 2,
        memory_limit_mb=source.memory_limit_mb or 128, tests=[{"input": c.input, "expected": c.expected} for c in source.tests],
    )
    task = Task(owner_id=principal.user_id, status=PRIVATE, based_on_id=source.id)
    await _apply(session, task, body)
    session.add(task)
    await session.commit()
    return await views.full(session, task, principal)


@router.post("/{task_id}/submit", response_model=TaskOut)
async def submit(task_id: UUID, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> TaskOut:
    """Отправить задачу в публичный банк. Задачи модераторов публикуются сразу."""
    task = await access.editable(session, task_id, principal)
    if task.status not in (PRIVATE, REJECTED):
        raise ApiError(409, "invalid_status", "Задача уже опубликована или на проверке")
    if task.topic_id is None:
        raise ApiError(422, "topic_required", "Выберите тему — по рубрикатору задачу находят в банке")
    data = {"task_id": str(task.id), "title": task.title, "author_id": str(task.owner_id), "type": task.type}
    task.review_comment = None
    if access.is_staff(principal):
        task.status, task.published_at = PUBLISHED, datetime.now(UTC)
        await outbox.event(session, "assessment.task.published", data, actor_id=principal.user_id)
    else:
        task.status = PENDING
        await outbox.event(session, "assessment.task.submitted", data, actor_id=principal.user_id)
    await session.commit()
    return await views.full(session, task, principal)


@router.post("/{task_id}/unpublish", response_model=TaskOut)
async def unpublish(task_id: UUID, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)) -> TaskOut:
    task = await access.load(session, task_id, lock=True)
    if not (task.owner_id == principal.user_id or access.is_staff(principal)):
        raise ApiError(404, "task_not_found", "Задача не найдена")
    if task.status not in (PENDING, PUBLISHED):
        raise ApiError(409, "invalid_status", "Задача не опубликована")
    task.status = PRIVATE
    await outbox.event(
        session, "assessment.task.unpublished",
        {"task_id": str(task.id), "title": task.title, "author_id": str(task.owner_id)}, actor_id=principal.user_id,
    )
    await session.commit()
    return await views.full(session, task, principal)


@router.post("/{task_id}/topic", response_model=TaskOut)
async def move(
    task_id: UUID, body: TopicMove, principal: Principal = Depends(author), session: AsyncSession = Depends(db.session)
) -> TaskOut:
    """Перенести задачу в другую тему: автор — свою, модератор — любую (например, при проверке)."""
    task = await access.load(session, task_id, lock=True)
    if not access.is_staff(principal):
        if task.owner_id != principal.user_id:
            raise ApiError(404, "task_not_found", "Задача не найдена")
        if task.status not in (PRIVATE, REJECTED):
            raise ApiError(409, "task_locked", "Задача на проверке или опубликована — тему меняет модератор")
    await _set_topic(session, task, body.topic_id)
    await session.commit()
    return await views.full(session, task, principal)
