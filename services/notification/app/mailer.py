import logging
from email.message import EmailMessage

import aiosmtplib

from .config import settings

log = logging.getLogger(__name__)


async def send_email(to: str, subject: str, text: str, html: str) -> None:
    if not settings.email_enabled:
        # Адрес и тема — без текста письма: в нём могут быть коды.
        log.info("почта выключена, письмо не отправлено: %s — %s", to, subject.split(" — ")[0])
        return
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        start_tls=settings.smtp_use_tls,
        timeout=15,
    )
