"""Обработчики сообщений из RabbitMQ."""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.messaging import Envelope

from . import mailer
from .models import EmailDelivery, Notification
from .templates import render

log = logging.getLogger(__name__)


async def on_email_command(envelope: Envelope, session: AsyncSession) -> None:
    """Команда notification.email.send: {"to", "template", "params"}."""
    data = envelope.data
    subject, text, html = render(data["template"], data.get("params", {}))
    session.add(EmailDelivery(command_id=envelope.event_id, to=data["to"], template=data["template"]))
    # Запись о доставке сохраняется в одной транзакции с inbox уже после отправки:
    # если отправка упадёт, сообщение уйдёт на повтор.
    await mailer.send_email(data["to"], subject, text, html)
    log.info("email sent", extra={"template": data["template"], "command_id": str(envelope.event_id)})


async def on_identity_event(envelope: Envelope, session: AsyncSession) -> None:
    if envelope.type == "identity.user.email_verified":
        session.add(
            Notification(
                user_id=UUID(envelope.data["user_id"]),
                kind="welcome",
                title="Добро пожаловать в Тестматику!",
                body="Ваш email подтверждён. Здесь будут появляться уведомления о занятиях, заданиях и сообщениях.",
            )
        )
