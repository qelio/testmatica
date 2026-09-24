from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError
from testmatica_common.ids import uuid7

from .. import otp, ratelimit, sessions
from ..deps import db, outbox
from ..models import STATUS_ACTIVE, STATUS_BANNED, STATUS_PENDING, Consent, User
from ..schemas import (
    Authenticated,
    ChallengeResponse,
    CodeRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    ResendRequest,
    ResetPasswordRequest,
    TwoFactorRequired,
)
from ..security import hash_password, mask_email, verify_password
from ..users import create_user, find_by_email, find_by_identifier, normalize

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_CREDENTIALS = ApiError(401, "invalid_credentials", "Неверный логин или пароль")


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=RegisterResponse)
async def register(
    body: RegisterRequest, request: Request, session: AsyncSession = Depends(db.session)
) -> RegisterResponse:
    if await find_by_email(session, body.email):
        raise ApiError(409, "email_taken", "Пользователь с таким email уже зарегистрирован")
    user = await create_user(
        session,
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        roles=[body.role],
        status=STATUS_PENDING,
    )
    session.add(
        Consent(user_id=user.id, type="pdn", version=body.consent_version, ip=sessions.client_ip(request))
    )
    challenge = await otp.issue(session, user, otp.PURPOSE_EMAIL_VERIFICATION)
    try:
        await session.commit()
    except IntegrityError:
        raise ApiError(409, "email_taken", "Пользователь с таким email уже зарегистрирован") from None
    return RegisterResponse(
        user_id=user.id, challenge_id=challenge.id, destination=mask_email(challenge.destination)
    )


@router.post("/verify-email", response_model=Authenticated)
async def verify_email(
    body: CodeRequest, request: Request, response: Response, session: AsyncSession = Depends(db.session)
) -> Authenticated:
    """Подтверждение email сразу открывает сессию: код подтверждения выдаётся только
    после ввода пароля (регистрация или вход), так что это уже два фактора."""
    challenge = await otp.verify(session, body.challenge_id, body.code, otp.PURPOSE_EMAIL_VERIFICATION)
    user = await session.get(User, challenge.user_id)
    assert user is not None
    if user.status != STATUS_PENDING:
        raise INVALID_CREDENTIALS
    _mark_email_verified(user)
    await outbox.event(
        session, "identity.user.email_verified", {"user_id": str(user.id)}, actor_id=user.id
    )
    result = await sessions.start_session(session, user, request, response)
    await session.commit()
    return result


@router.post("/resend-code", status_code=status.HTTP_202_ACCEPTED)
async def resend_code(body: ResendRequest, session: AsyncSession = Depends(db.session)) -> dict:
    await otp.resend(session, body.challenge_id)
    await session.commit()
    return {"status": "sent"}


@router.post("/login", response_model=TwoFactorRequired | Authenticated)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db.session),
) -> TwoFactorRequired | Authenticated:
    identifier = normalize(body.identifier)
    ip = sessions.client_ip(request)
    await ratelimit.check_login_allowed(identifier, ip)

    user = await find_by_identifier(session, identifier)
    if not verify_password(user.password_hash if user else None, body.password) or user is None:
        await ratelimit.register_login_failure(identifier, ip)
        await outbox.event(
            session,
            "identity.user.login_failed",
            {"user_id": str(user.id) if user else None, "ip": ip},
            actor_id=user.id if user else None,
        )
        await session.commit()
        raise INVALID_CREDENTIALS
    if user.status == STATUS_BANNED:
        raise ApiError(403, "account_banned", "Аккаунт заблокирован. Обратитесь в поддержку.")
    if user.status not in (STATUS_ACTIVE, STATUS_PENDING):
        raise INVALID_CREDENTIALS
    await ratelimit.reset_login_failures(identifier)

    if user.status == STATUS_PENDING:
        challenge = await otp.issue(session, user, otp.PURPOSE_EMAIL_VERIFICATION)
        await session.commit()
        raise ApiError(
            403,
            "email_not_verified",
            "Подтвердите email — мы отправили новый код",
            {"challenge_id": str(challenge.id), "destination": mask_email(challenge.destination)},
        )

    if user.two_factor_method is None:
        # Ученик, созданный педагогом без email и телефона (decisions.md, п. 6).
        result = await sessions.start_session(session, user, request, response)
        await session.commit()
        return result

    challenge = await otp.issue(session, user, otp.PURPOSE_LOGIN)
    await session.commit()
    return TwoFactorRequired(
        challenge_id=challenge.id, method=user.two_factor_method, destination=mask_email(challenge.destination)
    )


@router.post("/login/verify", response_model=Authenticated)
async def login_verify(
    body: CodeRequest, request: Request, response: Response, session: AsyncSession = Depends(db.session)
) -> Authenticated:
    challenge = await otp.verify(session, body.challenge_id, body.code, otp.PURPOSE_LOGIN)
    user = await session.get(User, challenge.user_id)
    if user is None or user.status != STATUS_ACTIVE:
        raise INVALID_CREDENTIALS
    result = await sessions.start_session(session, user, request, response)
    await session.commit()
    return result


@router.post("/refresh", response_model=Authenticated)
async def refresh(
    request: Request, response: Response, session: AsyncSession = Depends(db.session)
) -> Authenticated:
    result = await sessions.rotate(session, request, response)
    await session.commit()
    return result


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, session: AsyncSession = Depends(db.session)) -> None:
    await sessions.revoke_by_cookie(session, request)
    await session.commit()
    sessions.clear_cookie(response)


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED, response_model=ChallengeResponse)
async def forgot_password(
    body: ForgotPasswordRequest, session: AsyncSession = Depends(db.session)
) -> ChallengeResponse:
    user = await find_by_email(session, body.email)
    if user is None or user.status not in (STATUS_ACTIVE, STATUS_PENDING):
        # Ответ не отличается от успешного: нельзя проверить, зарегистрирован ли email.
        return ChallengeResponse(challenge_id=uuid7())
    challenge = await otp.issue(session, user, otp.PURPOSE_PASSWORD_RESET)
    await session.commit()
    return ChallengeResponse(challenge_id=challenge.id)


@router.post("/password/reset")
async def reset_password(body: ResetPasswordRequest, session: AsyncSession = Depends(db.session)) -> dict:
    challenge = await otp.verify(session, body.challenge_id, body.code, otp.PURPOSE_PASSWORD_RESET)
    user = await session.get(User, challenge.user_id)
    assert user is not None
    user.password_hash = hash_password(body.new_password)
    if user.status == STATUS_PENDING:
        # Код пришёл на почту — значит, email подтверждён.
        _mark_email_verified(user)
    await sessions.revoke_all(session, user.id, sessions.REASON_PASSWORD_RESET)
    await outbox.event(session, "identity.user.password_reset", {"user_id": str(user.id)}, actor_id=user.id)
    await session.commit()
    return {"status": "password_changed"}


def _mark_email_verified(user: User) -> None:
    user.status = STATUS_ACTIVE
    user.email_verified_at = datetime.now(UTC)
    if user.two_factor_method is None:
        user.two_factor_method = "email"
