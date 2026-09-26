from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal
from testmatica_common.errors import ApiError

from ..deps import auth, db
from ..models import STATUS_ACTIVE, User
from ..schemas import UserOut

router = APIRouter(prefix="/me", tags=["me"])


async def _load(session: AsyncSession, principal: Principal) -> User:
    user = await session.get(User, principal.user_id)
    if user is None or user.status != STATUS_ACTIVE:
        raise ApiError(401, "invalid_token", "Пользователь не найден или заблокирован")
    return user


@router.get("", response_model=UserOut)
async def me(
    principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)
) -> UserOut:
    return UserOut.of(await _load(session, principal))
