"""Обращения в поддержку: пользователь пишет, модераторы и администраторы отвечают (решение №26).

Переписка — обычный чат поддержки (вложения, реальное время, уведомления); здесь — тема, категория,
статус, кто ведёт обращение, и очередь для поддержки: подписчики «Базового» — первыми."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import Principal
from testmatica_common.errors import ApiError

from .. import realtime
from ..deals import _post
from ..deps import auth, db, outbox, plans
from ..models import (
    KIND_SUPPORT,
    TICKET_CATEGORIES,
    TICKET_CLOSED,
    TICKET_OPEN,
    Conversation,
    ConversationMember,
    Message,
    Person,
    SupportTicket,
)
from ..schemas import MessageCreate
from ..support import _staff
from ..tickets import is_staff
from .conversations import send_message

router = APIRouter(prefix="/support", tags=["support"])

Category = Literal["account", "lessons", "tests", "tutors", "payments", "bug", "idea", "other"]
assert set(TICKET_CATEGORIES) == set(Category.__args__)  # type: ignore[attr-defined]


class TicketCreate(BaseModel):
    category: Category
    subject: str = Field(min_length=3, max_length=200)
    text: str = Field(min_length=1, max_length=4000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=10)

    @field_validator("subject", "text")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Заполните поле")
        return v


class TicketOut(BaseModel):
    id: UUID
    category: str
    subject: str
    status: str
    priority: bool
    requester_id: UUID
    requester_name: str
    requester_roles: list[str]
    assignee_id: UUID | None
    assignee_name: str | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    unread: int = Field(description="Непрочитанных сообщений для того, кто смотрит")
    last_text: str | None


class QueueCounts(BaseModel):
    open: int
    mine_open: int


async def _out(session: AsyncSession, tickets: list[SupportTicket], viewer: UUID) -> list[TicketOut]:
    if not tickets:
        return []
    ids = [t.id for t in tickets]
    people = {p.user_id: p for p in (await session.execute(
        select(Person).where(Person.user_id.in_({t.requester_id for t in tickets} | {t.assignee_id for t in tickets if t.assignee_id}))
    )).scalars()}
    reads = dict((await session.execute(
        select(ConversationMember.conversation_id, ConversationMember.last_read_at)
        .where(ConversationMember.conversation_id.in_(ids), ConversationMember.user_id == viewer)
    )).all())
    unread = dict((await session.execute(
        select(Message.conversation_id, func.count())
        .join(ConversationMember, (ConversationMember.conversation_id == Message.conversation_id) & (ConversationMember.user_id == viewer))
        .where(Message.conversation_id.in_(ids), Message.author_id != viewer, Message.deleted_at.is_(None),
               (ConversationMember.last_read_at.is_(None)) | (Message.created_at > ConversationMember.last_read_at))
        .group_by(Message.conversation_id)
    )).all())
    # Последнее несистемное сообщение каждого обращения — для превью в списке.
    last = {m.conversation_id: m for m in (await session.execute(
        select(Message).distinct(Message.conversation_id)
        .where(Message.conversation_id.in_(ids), Message.is_system.is_(False))
        .order_by(Message.conversation_id, Message.created_at.desc())
    )).scalars()}
    out = []
    for t in tickets:
        req, asg = people.get(t.requester_id), people.get(t.assignee_id) if t.assignee_id else None
        msg = last.get(t.id)
        out.append(TicketOut(
            id=t.id, category=t.category, subject=t.subject, status=t.status, priority=t.priority,
            requester_id=t.requester_id, requester_name=req.full_name if req else "Пользователь", requester_roles=req.roles if req else [],
            assignee_id=t.assignee_id, assignee_name=asg.full_name if asg else None,
            created_at=t.created_at, updated_at=t.updated_at, closed_at=t.closed_at,
            unread=unread.get(t.id, 0) if t.id in reads else 0,
            last_text=(None if msg is None or msg.deleted_at else (msg.text or "📎 вложение")),
        ))
    return out


async def _ticket(session: AsyncSession, ticket_id: UUID, p: Principal, lock: bool = False) -> SupportTicket:
    t = await session.get(SupportTicket, ticket_id, with_for_update=lock)
    if t is None or (t.requester_id != p.user_id and not is_staff(p)):
        raise ApiError(404, "ticket_not_found", "Обращение не найдено")
    return t


async def _system(session: AsyncSession, t: SupportTicket, author: UUID, text: str) -> None:
    members = list((await session.execute(
        select(ConversationMember.user_id).where(ConversationMember.conversation_id == t.id, ConversationMember.left_at.is_(None))
    )).scalars())
    await _post(session, t.id, author, text, True, members)


async def _name(session: AsyncSession, user_id: UUID) -> str:
    p = await session.get(Person, user_id)
    return p.full_name if p else "Сотрудник поддержки"


@router.post("/tickets", response_model=TicketOut, status_code=201)
async def create_ticket(body: TicketCreate, principal: Principal = Depends(auth.principal),
                        session: AsyncSession = Depends(db.session)) -> TicketOut:
    """Новое обращение: чат с поддержкой (все модераторы и администраторы) и первое сообщение."""
    if is_staff(principal):
        raise ApiError(403, "forbidden", "Сотрудники поддержки обращения не создают")
    priority = (await plans.many([principal.user_id], fallback="free")).get(principal.user_id) == "basic"
    conv = Conversation(kind=KIND_SUPPORT, title=f"Обращение: {body.subject}")
    session.add(conv)
    await session.flush()
    session.add(ConversationMember(conversation_id=conv.id, user_id=principal.user_id, role="member"))
    for uid in await _staff(session):
        if uid != principal.user_id:
            session.add(ConversationMember(conversation_id=conv.id, user_id=uid, role="staff"))
    ticket = SupportTicket(id=conv.id, requester_id=principal.user_id, category=body.category, subject=body.subject,
                           status=TICKET_OPEN, priority=priority)
    session.add(ticket)
    await outbox.event(session, "chat.ticket.created", {"ticket_id": str(conv.id), "category": body.category, "priority": priority},
                       actor_id=principal.user_id)
    await session.flush()
    # Первое сообщение — обычной отправкой: вложения, уведомления поддержке, реальное время.
    await send_message(conv.id, MessageCreate(text=body.text, attachment_ids=body.attachment_ids), principal, session)
    await session.refresh(ticket)
    [out] = await _out(session, [ticket], principal.user_id)
    return out


@router.get("/tickets", response_model=list[TicketOut])
async def my_tickets(principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> list[TicketOut]:
    rows = (await session.execute(
        select(SupportTicket).where(SupportTicket.requester_id == principal.user_id).order_by(SupportTicket.updated_at.desc())
    )).scalars().all()
    return await _out(session, list(rows), principal.user_id)


@router.get("/queue", response_model=list[TicketOut])
async def queue(
    status: Literal["open", "answered", "closed"] = Query("open"),
    mine: bool = Query(False, description="Только обращения, которые веду я"),
    principal: Principal = Depends(auth.principal),
    session: AsyncSession = Depends(db.session),
) -> list[TicketOut]:
    """Очередь поддержки. Ждущие ответа — подписчики первыми, дальше самые давние."""
    if not is_staff(principal):
        raise ApiError(403, "forbidden", "Очередь поддержки — для модераторов и администраторов")
    q = select(SupportTicket).where(SupportTicket.status == status)
    if mine:
        q = q.where(SupportTicket.assignee_id == principal.user_id)
    if status == TICKET_OPEN:
        q = q.order_by(SupportTicket.priority.desc(), SupportTicket.updated_at)
    else:
        q = q.order_by(SupportTicket.updated_at.desc())
    rows = (await session.execute(q.limit(200))).scalars().all()
    return await _out(session, list(rows), principal.user_id)


@router.get("/queue/counts", response_model=QueueCounts)
async def queue_counts(principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> QueueCounts:
    if not is_staff(principal):
        raise ApiError(403, "forbidden", "Очередь поддержки — для модераторов и администраторов")
    row = (await session.execute(
        select(func.count(), func.count(case((SupportTicket.assignee_id == principal.user_id, 1))))
        .where(SupportTicket.status == TICKET_OPEN)
    )).one()
    return QueueCounts(open=row[0], mine_open=row[1])


@router.get("/tickets/{ticket_id}", response_model=TicketOut)
async def get_ticket(ticket_id: UUID, principal: Principal = Depends(auth.principal),
                     session: AsyncSession = Depends(db.session)) -> TicketOut:
    t = await _ticket(session, ticket_id, principal)
    if is_staff(principal):
        # Сотрудник, пришедший после создания обращения, становится участником переписки.
        await session.execute(insert(ConversationMember).values(conversation_id=t.id, user_id=principal.user_id, role="staff")
                              .on_conflict_do_nothing())
        await session.commit()
    [out] = await _out(session, [t], principal.user_id)
    return out


@router.post("/tickets/{ticket_id}/assign", response_model=TicketOut)
async def assign(ticket_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> TicketOut:
    """Взять обращение себе."""
    t = await _ticket(session, ticket_id, principal, lock=True)
    if not is_staff(principal):
        raise ApiError(403, "forbidden", "Брать обращения может поддержка")
    if t.assignee_id != principal.user_id:
        t.assignee_id, t.updated_at = principal.user_id, datetime.now(UTC)
        await _system(session, t, principal.user_id, f"Обращением занимается {await _name(session, principal.user_id)}.")
    await session.commit()
    [out] = await _out(session, [t], principal.user_id)
    return out


@router.post("/tickets/{ticket_id}/close", response_model=TicketOut)
async def close(ticket_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> TicketOut:
    """Закрыть: автор — «вопрос решён», поддержка — «вопрос решён или ответ не нужен». Написать можно и после — обращение откроется."""
    t = await _ticket(session, ticket_id, principal, lock=True)
    if t.status != TICKET_CLOSED:
        now = datetime.now(UTC)
        t.status, t.closed_at, t.updated_at = TICKET_CLOSED, now, now
        who = "Автор закрыл обращение." if principal.user_id == t.requester_id else "Поддержка закрыла обращение."
        await _system(session, t, principal.user_id, f"{who} Если вопрос остался — просто напишите сюда.")
        await outbox.event(session, "chat.ticket.closed", {"ticket_id": str(t.id)}, actor_id=principal.user_id)
    await session.commit()
    await realtime.publish([t.requester_id], {"type": "refresh", "conversation_id": str(t.id)})
    [out] = await _out(session, [t], principal.user_id)
    return out


@router.post("/tickets/{ticket_id}/reopen", response_model=TicketOut)
async def reopen(ticket_id: UUID, principal: Principal = Depends(auth.principal), session: AsyncSession = Depends(db.session)) -> TicketOut:
    t = await _ticket(session, ticket_id, principal, lock=True)
    if t.status == TICKET_CLOSED:
        t.status, t.closed_at, t.updated_at = TICKET_OPEN, None, datetime.now(UTC)
        await _system(session, t, principal.user_id, "Обращение открыто снова.")
    await session.commit()
    [out] = await _out(session, [t], principal.user_id)
    return out
