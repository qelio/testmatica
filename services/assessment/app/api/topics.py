"""Рубрикатор банка задач: предмет → раздел → тема. Смотрят все авторы, правят модераторы."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_MODERATOR, ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from ..deps import auth, db
from ..models import PUBLISHED, Task, Topic
from ..schemas import TopicIn, TopicOut, TopicUpdate

router = APIRouter(prefix="/topics", tags=["topics"])
moderator = auth.require(ROLE_MODERATOR)


def _out(t: Topic, count: int = 0) -> TopicOut:
    return TopicOut(id=t.id, subject_id=t.subject_id, subject_name=t.subject_name, parent_id=t.parent_id, title=t.title,
                    position=t.position, count=count)


@router.get("", response_model=list[TopicOut])
async def tree(
    scope: str = Query("public", pattern="^(public|mine)$"),
    principal: Principal = Depends(auth.require(ROLE_TEACHER, ROLE_MODERATOR)),
    session: AsyncSession = Depends(db.session),
) -> list[TopicOut]:
    """Весь рубрикатор плоским списком (дерево собирает клиент) и число задач в каждом узле."""
    counted = select(Task.topic_id, func.count()).where(Task.topic_id.is_not(None))
    counted = counted.where(Task.owner_id == principal.user_id) if scope == "mine" else counted.where(Task.status == PUBLISHED)
    counts = dict((await session.execute(counted.group_by(Task.topic_id))).all())
    topics = (await session.execute(select(Topic).order_by(Topic.subject_name, Topic.position, Topic.title))).scalars()
    return [_out(t, counts.get(t.id, 0)) for t in topics]


@router.post("", response_model=TopicOut, status_code=201)
async def create(body: TopicIn, _: Principal = Depends(moderator), session: AsyncSession = Depends(db.session)) -> TopicOut:
    """Раздел (без parent_id, нужен предмет) или тема внутри раздела. Глубже двух уровней не вкладываем."""
    if body.parent_id:
        parent = await session.get(Topic, body.parent_id)
        if parent is None:
            raise ApiError(404, "topic_not_found", "Раздел не найден")
        if parent.parent_id is not None:
            raise ApiError(422, "too_deep", "Темы добавляются только в разделы")
        subject_id, subject_name = parent.subject_id, parent.subject_name
    else:
        if body.subject_id is None or not body.subject_name:
            raise ApiError(422, "subject_required", "Выберите предмет")
        subject_id, subject_name = body.subject_id, body.subject_name
    siblings = Topic.parent_id == body.parent_id if body.parent_id else Topic.parent_id.is_(None)
    last = await session.scalar(select(func.max(Topic.position)).where(Topic.subject_id == subject_id, siblings))
    topic = Topic(subject_id=subject_id, subject_name=subject_name, parent_id=body.parent_id, title=body.title,
                  position=(last + 1) if last is not None else 0)
    session.add(topic)
    await session.commit()
    return _out(topic)


@router.patch("/{topic_id}", response_model=TopicOut)
async def update(
    topic_id: UUID, body: TopicUpdate, _: Principal = Depends(moderator), session: AsyncSession = Depends(db.session)
) -> TopicOut:
    topic = await session.get(Topic, topic_id, with_for_update=True)
    if topic is None:
        raise ApiError(404, "topic_not_found", "Тема не найдена")
    if body.title is not None:
        topic.title = body.title
    if body.position is not None:
        topic.position = body.position
    await session.commit()
    return _out(topic)


@router.delete("/{topic_id}", status_code=204)
async def delete(topic_id: UUID, _: Principal = Depends(moderator), session: AsyncSession = Depends(db.session)) -> None:
    """Удалить можно только пустой узел: без вложенных тем и без задач (в том числе чужих черновиков)."""
    topic = await session.get(Topic, topic_id, with_for_update=True)
    if topic is None:
        raise ApiError(404, "topic_not_found", "Тема не найдена")
    if await session.scalar(select(func.count()).select_from(Topic).where(Topic.parent_id == topic_id)):
        raise ApiError(409, "topic_not_empty", "Сначала удалите или перенесите темы раздела")
    if await session.scalar(select(func.count()).select_from(Task).where(Task.topic_id == topic_id)):
        raise ApiError(409, "topic_not_empty", "В теме есть задачи — перенесите их в другую тему")
    await session.delete(topic)
    await session.commit()
