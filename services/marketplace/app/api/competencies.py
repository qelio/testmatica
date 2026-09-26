"""Справочник компетенций по предметам — для полей заявки «Что уже знаю» и «Что хочу получить»."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_MODERATOR, Principal
from testmatica_common.errors import ApiError

from .. import profiles
from ..deps import auth, db
from ..models import Competency, LessonRequest
from ..schemas import CompetencyIn, CompetencyOut, CompetencyUpdate

router = APIRouter(prefix="/competencies", tags=["competencies"])
moderator = auth.require(ROLE_MODERATOR)
log = logging.getLogger(__name__)

DEFAULTS: dict[str, list[str]] = {
    "Математика": ["Арифметика и дроби", "Проценты", "Текстовые задачи", "Уравнения", "Геометрия на плоскости", "Вероятность и статистика"],
    "Алгебра": ["Выражения и степени", "Линейные уравнения", "Квадратные уравнения", "Неравенства", "Функции и графики",
                "Тригонометрия", "Логарифмы", "Производная"],
    "Геометрия": ["Треугольники", "Четырёхугольники", "Окружность", "Векторы", "Стереометрия"],
    "Информатика": ["Основы Python", "Алгоритмы", "Структуры данных", "Системы счисления", "Логика", "Задачи ЕГЭ с кодом"],
    "Физика": ["Кинематика", "Динамика", "Законы сохранения", "Термодинамика", "Электричество", "Оптика"],
    "Русский язык": ["Орфография", "Пунктуация", "Грамматика", "Сочинение", "Изложение"],
    "Английский язык": ["Грамматика", "Лексика", "Разговорная речь", "Аудирование", "Письмо", "Подготовка к экзамену"],
}


def _out(c: Competency) -> CompetencyOut:
    return CompetencyOut(id=c.id, subject_id=c.subject_id, title=c.title, position=c.position)


@router.get("", response_model=list[CompetencyOut])
async def competencies(subject_id: UUID, session: AsyncSession = Depends(db.session)) -> list[CompetencyOut]:
    rows = await session.execute(select(Competency).where(Competency.subject_id == subject_id).order_by(Competency.position, Competency.title))
    return [_out(c) for c in rows.scalars()]


@router.post("", response_model=CompetencyOut, status_code=201)
async def create(body: CompetencyIn, _: Principal = Depends(moderator), session: AsyncSession = Depends(db.session)) -> CompetencyOut:
    if str(body.subject_id) not in await profiles.subjects():
        raise ApiError(422, "unknown_subject", "Такого предмета нет в справочнике")
    last = await session.scalar(select(func.max(Competency.position)).where(Competency.subject_id == body.subject_id))
    c = Competency(subject_id=body.subject_id, title=body.title, position=(last or 0) + 1)
    session.add(c)
    await session.commit()
    return _out(c)


@router.patch("/{competency_id}", response_model=CompetencyOut)
async def update(
    competency_id: UUID, body: CompetencyUpdate, _: Principal = Depends(moderator), session: AsyncSession = Depends(db.session)
) -> CompetencyOut:
    c = await session.get(Competency, competency_id, with_for_update=True)
    if c is None:
        raise ApiError(404, "competency_not_found", "Компетенция не найдена")
    if body.title:
        c.title = " ".join(body.title.split())
    if body.position is not None:
        c.position = body.position
    await session.commit()
    return _out(c)


@router.delete("/{competency_id}", status_code=204)
async def delete(competency_id: UUID, _: Principal = Depends(moderator), session: AsyncSession = Depends(db.session)) -> None:
    c = await session.get(Competency, competency_id)
    if c is None:
        raise ApiError(404, "competency_not_found", "Компетенция не найдена")
    used = await session.scalar(select(func.count()).select_from(LessonRequest).where(
        LessonRequest.current_ids.contains([c.id]) | LessonRequest.desired_ids.contains([c.id])))
    if used:
        raise ApiError(409, "competency_in_use", "Компетенция указана в заявках — её можно переименовать, но не удалить")
    await session.delete(c)
    await session.commit()


async def ensure_defaults() -> None:
    """Фоновая задача: базовый справочник, пока модераторы его не завели (предметы — из content)."""
    async with db.sessionmaker() as session, session.begin():
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('marketplace.competencies.seed'))"))
        if await session.scalar(select(func.count()).select_from(Competency)):
            return
        subjects = await profiles.subjects()
        created = 0
        for sid, name in subjects.items():
            for i, title in enumerate(DEFAULTS.get(name, [])):
                session.add(Competency(subject_id=UUID(sid), title=title, position=i))
                created += 1
    log.info("default competencies created", extra={"count": created})
