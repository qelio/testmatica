"""Расписание звонков педагога (решение №55) — полосами уроков в календаре."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal

from ..deps import auth, db
from ..models import BellSchedule
from ..schemas import BellScheduleIn, BellScheduleOut

router = APIRouter(prefix="/bells", tags=["bells"])
teacher = auth.require(ROLE_TEACHER)


@router.get("", response_model=BellScheduleOut)
async def get_bells(principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> BellScheduleOut:
    """Своё расписание звонков; не задано — пустой список уроков."""
    bells = await session.get(BellSchedule, principal.user_id)
    if bells is None:
        return BellScheduleOut()
    return BellScheduleOut(periods=bells.periods, weekdays=bells.weekdays)


@router.put("", response_model=BellScheduleOut)
async def save_bells(
    body: BellScheduleIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> BellScheduleOut:
    bells = await session.get(BellSchedule, principal.user_id, with_for_update=True) or BellSchedule(teacher_id=principal.user_id)
    bells.periods = [p.model_dump() for p in body.periods]
    bells.weekdays = body.weekdays
    session.add(bells)
    await session.commit()
    return BellScheduleOut(periods=bells.periods, weekdays=bells.weekdays)
