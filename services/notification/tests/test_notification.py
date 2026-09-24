from uuid import uuid4

import pytest
from testmatica_common.testing import make_envelope

from app import handlers
from app.templates import UnknownTemplate, render

from .conftest import bearer, consumer


def email_command(template="login", **params):
    return make_envelope(
        "notification.email.send",
        {"to": "u@example.com", "template": template, "params": {"name": "Аня", "code": "123456", "ttl_minutes": 10, **params}},
    )


async def test_email_command_sends_once(sent_emails):
    c = consumer("notification.email", handlers.on_email_command)
    command = email_command()

    assert await c.process(command) is True
    # Повторная доставка того же сообщения не отправляет второе письмо.
    assert await c.process(command) is False

    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == "u@example.com"
    assert "123456" in sent_emails[0]["subject"]
    assert "Аня" in sent_emails[0]["text"]


async def test_failed_send_is_not_marked_processed(monkeypatch):
    async def broken(*_):
        raise ConnectionError("smtp down")

    monkeypatch.setattr(handlers.mailer, "send_email", broken)
    c = consumer("notification.email", handlers.on_email_command)
    command = email_command()
    with pytest.raises(ConnectionError):
        await c.process(command)

    # После восстановления SMTP повторная попытка должна пройти.
    sent = []

    async def ok(to, *_):
        sent.append(to)

    monkeypatch.setattr(handlers.mailer, "send_email", ok)
    assert await c.process(command) is True
    assert sent == ["u@example.com"]


def test_html_is_escaped():
    _, _, html = render("login", {"name": "<script>", "code": "1", "ttl_minutes": 1})
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_unknown_template():
    with pytest.raises(UnknownTemplate):
        render("nope", {})


async def test_welcome_notification_and_api(client):
    user_id = uuid4()
    c = consumer("notification.identity", handlers.on_identity_event)
    await c.process(make_envelope("identity.user.email_verified", {"user_id": str(user_id)}))
    await c.process(make_envelope("identity.user.logged_in", {"user_id": str(user_id)}))

    resp = await client.get("/notifications", headers=bearer(user_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["unread"] == 1
    assert body["items"][0]["kind"] == "welcome"

    other = await client.get("/notifications", headers=bearer(uuid4()))
    assert other.json() == {"items": [], "unread": 0}

    nid = body["items"][0]["id"]
    assert (await client.post(f"/notifications/{nid}/read", headers=bearer(uuid4()))).status_code == 404
    assert (await client.post(f"/notifications/{nid}/read", headers=bearer(user_id))).status_code == 204
    assert (await client.get("/notifications", headers=bearer(user_id))).json()["unread"] == 0


async def test_api_requires_token(client):
    assert (await client.get("/notifications")).status_code == 401
