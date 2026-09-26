"""Справочник предметов платформы — ведут модераторы. Им пользуются библиотека, банк задач, группы, занятия, маркетплейс."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_MODERATOR, Principal
from testmatica_common.errors import ApiError

from ..deps import auth, db, outbox
from ..models import Subject
from ..schemas import SubjectIn, SubjectOut, SubjectUpdate

router = APIRouter(prefix="/subjects", tags=["subjects"])
moderator = auth.require(ROLE_MODERATOR)


def _out(s: Subject) -> SubjectOut:
    return SubjectOut(id=s.id, name=s.name, hidden=s.hidden)


def _clean(name: str) -> str:
    return " ".join(name.split())


@router.get("", response_model=list[SubjectOut])
async def subjects(
    all: bool = Query(False, description="Со скрытыми — для модератора"), session: AsyncSession = Depends(db.session)
) -> list[SubjectOut]:
    """Список для выбора (без скрытых). Открыт без входа: нужен публичному поиску и каталогу."""
    query = select(Subject).order_by(Subject.position, Subject.name)
    if not all:
        query = query.where(Subject.hidden.is_(False))
    return [_out(s) for s in (await session.execute(query)).scalars()]


async def _event(session: AsyncSession, s: Subject, p: Principal, old_name: str | None = None) -> None:
    # Названия предметов хранят и другие сервисы (задачи, профили, группы, занятия) — они обновятся по событию.
    await outbox.event(session, "content.subject.updated",
                       {"subject_id": str(s.id), "name": s.name, "old_name": old_name or s.name, "hidden": s.hidden},
                       actor_id=p.user_id)


@router.post("", response_model=SubjectOut, status_code=201)
async def create(body: SubjectIn, principal: Principal = Depends(moderator), session: AsyncSession = Depends(db.session)) -> SubjectOut:
    name = _clean(body.name)
    if await session.scalar(select(Subject.id).where(func.lower(Subject.name) == name.lower())):
        raise ApiError(409, "subject_exists", "Такой предмет уже есть")
    last = await session.scalar(select(func.max(Subject.position)))
    s = Subject(name=name, position=(last or 0) + 1)
    session.add(s)
    await session.flush()
    await _event(session, s, principal)
    await session.commit()
    return _out(s)


@router.patch("/{subject_id}", response_model=SubjectOut)
async def update(
    subject_id: UUID, body: SubjectUpdate, principal: Principal = Depends(moderator), session: AsyncSession = Depends(db.session)
) -> SubjectOut:
    s = await session.get(Subject, subject_id, with_for_update=True)
    if s is None:
        raise ApiError(404, "subject_not_found", "Предмет не найден")
    old_name = s.name
    if body.name is not None:
        name = _clean(body.name)
        clash = await session.scalar(select(Subject.id).where(func.lower(Subject.name) == name.lower(), Subject.id != s.id))
        if clash:
            raise ApiError(409, "subject_exists", "Такой предмет уже есть")
        s.name = name
    if body.hidden is not None:
        s.hidden = body.hidden
    if body.position is not None:
        s.position = body.position
    await _event(session, s, principal, old_name)
    await session.commit()
    return _out(s)
