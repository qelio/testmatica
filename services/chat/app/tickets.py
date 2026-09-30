"""Статусы обращений в поддержку меняются сами, когда в переписке кто-то пишет."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_ADMIN, ROLE_MODERATOR, Principal

from .models import TICKET_ANSWERED, TICKET_OPEN, SupportTicket


def is_staff(p: Principal) -> bool:
    return p.has_any(ROLE_MODERATOR, ROLE_ADMIN)


async def on_message(session: AsyncSession, conversation_id: UUID, principal: Principal) -> None:
    """Ответ поддержки → «ответили» (и обращение закрепляется за ответившим, если ничьё);
    сообщение автора → «ждёт ответа» (закрытое открывается снова)."""
    ticket = await session.get(SupportTicket, conversation_id, with_for_update=True)
    if ticket is None:
        return  # чат спора по отзыву — без статусов
    now = datetime.now(UTC)
    if principal.user_id == ticket.requester_id:
        ticket.status, ticket.closed_at = TICKET_OPEN, None
    elif is_staff(principal):
        ticket.status = TICKET_ANSWERED
        ticket.assignee_id = ticket.assignee_id or principal.user_id
    ticket.updated_at = now
