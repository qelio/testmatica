"""Приглашение ученика по email: письмо со ссылкой, ученик регистрируется или входит и принимает."""

import secrets
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_STUDENT, ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import logic
from ..config import settings
from ..deps import auth, db, outbox
from ..models import SOURCE_INVITE, Group, Invitation
from ..people import name_of
from ..schemas import InvitationCreate, InvitationOut, InvitationPublic

router = APIRouter(prefix="/invitations", tags=["invitations"])
teacher = auth.require(ROLE_TEACHER)


def _group_text(group: Group | None) -> str:
    """Окончание фразы «приглашает вас заниматься…»."""
    if group is None:
        return ""
    return f" в {'классе' if group.kind == 'class' else 'группе'} «{group.title}»"


def _out(inv: Invitation) -> InvitationOut:
    return InvitationOut.model_validate(inv, from_attributes=True)


@router.get("", response_model=list[InvitationOut])
async def list_invitations(principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)):
    rows = await session.execute(
        select(Invitation)
        .where(
            Invitation.teacher_id == principal.user_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > logic.now(),
        )
        .order_by(Invitation.created_at.desc())
    )
    return [_out(i) for i in rows.scalars()]


@router.post("", response_model=InvitationOut, status_code=201)
async def create_invitation(
    body: InvitationCreate, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> InvitationOut:
    group = await logic.owned_group(session, body.group_id, principal.user_id) if body.group_id else None
    inv = Invitation(
        token=secrets.token_urlsafe(32),
        teacher_id=principal.user_id,
        email=body.email.lower(),
        group_id=group.id if group else None,
        expires_at=logic.now() + timedelta(days=settings.invitation_ttl_days),
    )
    session.add(inv)
    await session.flush()
    await outbox.command(
        session,
        queue="notification.email",
        type="notification.email.send",
        data={
            "to": inv.email,
            "template": "invitation",
            "params": {
                "teacher_name": await name_of(session, principal.user_id),
                "group_text": _group_text(group),
                "url": f"{settings.web_base_url}/invite/{inv.token}",
                "ttl_days": settings.invitation_ttl_days,
            },
        },
        actor_id=principal.user_id,
    )
    await outbox.event(
        session,
        "classroom.invitation.created",
        {"invitation_id": str(inv.id), "teacher_id": str(principal.user_id), "group_id": str(inv.group_id) if inv.group_id else None},
        actor_id=principal.user_id,
    )
    await session.commit()
    return _out(inv)


@router.delete("/{invitation_id}", status_code=204)
async def revoke_invitation(
    invitation_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)
) -> None:
    inv = await session.get(Invitation, invitation_id)
    if inv is None or inv.teacher_id != principal.user_id:
        raise ApiError(404, "invitation_not_found", "Приглашение не найдено")
    if inv.accepted_at is None and inv.revoked_at is None:
        inv.revoked_at = logic.now()
        await session.commit()


def _status(inv: Invitation) -> str:
    if inv.revoked_at is not None:
        return "revoked"
    if inv.accepted_at is not None:
        return "used"
    if inv.expires_at <= logic.now():
        return "expired"
    return "valid"


async def _by_token(session: AsyncSession, token: str, lock: bool = False) -> Invitation:
    query = select(Invitation).where(Invitation.token == token)
    if lock:
        query = query.with_for_update()
    inv = (await session.execute(query)).scalar_one_or_none()
    if inv is None:
        raise ApiError(404, "invitation_not_found", "Приглашение не найдено")
    return inv


@router.get("/token/{token}", response_model=InvitationPublic)
async def view_invitation(token: str, session: AsyncSession = Depends(db.session)) -> InvitationPublic:
    """Публичная информация о приглашении — показывается до входа."""
    inv = await _by_token(session, token)
    group = await session.get(Group, inv.group_id) if inv.group_id else None
    return InvitationPublic(
        status=_status(inv),
        teacher_name=await name_of(session, inv.teacher_id),
        group_title=group.title if group else None,
        group_kind=group.kind if group else None,
    )


@router.post("/token/{token}/accept", status_code=204)
async def accept_invitation(
    token: str,
    principal: Principal = Depends(auth.require(ROLE_STUDENT)),
    session: AsyncSession = Depends(db.session),
) -> None:
    inv = await _by_token(session, token, lock=True)
    status = _status(inv)
    if status != "valid":
        messages = {
            "used": "Приглашение уже использовано",
            "expired": "Срок приглашения истёк — попросите педагога отправить новое",
            "revoked": "Приглашение отменено педагогом",
        }
        raise ApiError(410, f"invitation_{status}", messages[status])
    inv.accepted_at = logic.now()
    inv.accepted_by = principal.user_id
    await logic.activate_link(session, inv.teacher_id, principal.user_id, SOURCE_INVITE, principal.user_id)
    if inv.group_id:
        group = await session.get(Group, inv.group_id)
        if group is not None and group.archived_at is None:
            await logic.add_member(session, group, principal.user_id, principal.user_id)
    await session.commit()
