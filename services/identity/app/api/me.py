from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from ..config import settings
from ..deps import auth, db, issuer, outbox
from ..models import STATUS_ACTIVE, User
from ..schemas import Authenticated, TeacherModeRequest, UserOut

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


@router.put("/teacher-mode", response_model=Authenticated)
async def switch_teacher_mode(
    body: TeacherModeRequest,
    principal: Principal = Depends(auth.require(ROLE_TEACHER)),
    session: AsyncSession = Depends(db.session),
) -> Authenticated:
    """Переключатель «Школьный учитель ↔ Репетитор». Режим записан в токене,
    поэтому в ответе сразу новый access-токен."""
    user = await _load(session, principal)
    if user.teacher_mode != body.mode:
        user.teacher_mode = body.mode
        await outbox.event(
            session,
            "identity.user.teacher_mode_changed",
            {"user_id": str(user.id), "mode": body.mode},
            actor_id=user.id,
        )
        await session.commit()
    return Authenticated(
        access_token=issuer.access_token(user),
        expires_in=settings.access_token_ttl_seconds,
        user=UserOut.of(user),
    )
