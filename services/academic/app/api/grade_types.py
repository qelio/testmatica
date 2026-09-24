"""Справочник типов оценок: читают все, меняет модератор."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_MODERATOR, Principal
from testmatica_common.errors import ApiError

from ..deps import auth, db, outbox
from ..models import GradeType
from ..schemas import GradeTypeCreate, GradeTypeOut, GradeTypeUpdate

router = APIRouter(prefix="/grade-types", tags=["grade-types"])
moderator = auth.require(ROLE_MODERATOR)


def _out(t: GradeType) -> GradeTypeOut:
    return GradeTypeOut.model_validate(t, from_attributes=True)


@router.get("", response_model=list[GradeTypeOut])
async def list_types(
    all: bool = False, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> list[GradeTypeOut]:
    query = select(GradeType).order_by(GradeType.position, GradeType.name)
    if not (all and principal.has_any(ROLE_MODERATOR)):
        query = query.where(GradeType.is_active.is_(True))
    return [_out(t) for t in (await session.execute(query)).scalars()]


@router.post("", response_model=GradeTypeOut, status_code=201)
async def create_type(
    body: GradeTypeCreate, principal: Principal = Depends(moderator), session: AsyncSession = Depends(db.session)
) -> GradeTypeOut:
    grade_type = GradeType(name=body.name, position=body.position)
    session.add(grade_type)
    await _save(session, grade_type, "academic.grade_type.created", principal)
    return _out(grade_type)


@router.patch("/{type_id}", response_model=GradeTypeOut)
async def update_type(
    type_id: UUID,
    body: GradeTypeUpdate,
    principal: Principal = Depends(moderator),
    session: AsyncSession = Depends(db.session),
) -> GradeTypeOut:
    grade_type = await session.get(GradeType, type_id)
    if grade_type is None:
        raise ApiError(404, "grade_type_not_found", "Тип оценки не найден")
    for field, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(grade_type, field, value.strip() if isinstance(value, str) else value)
    await _save(session, grade_type, "academic.grade_type.updated", principal)
    return _out(grade_type)


async def _save(session: AsyncSession, grade_type: GradeType, event: str, principal: Principal) -> None:
    try:
        await session.flush()
    except IntegrityError:
        raise ApiError(409, "grade_type_exists", "Такой тип оценки уже есть") from None
    await outbox.event(
        session,
        event,
        {"grade_type_id": str(grade_type.id), "name": grade_type.name, "is_active": grade_type.is_active},
        actor_id=principal.user_id,
    )
    await session.commit()
