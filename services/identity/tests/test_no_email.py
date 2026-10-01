"""Режим без почтового сервера (EMAIL_CODES=false, решение №29)."""

import pytest

from app.config import settings

from .conftest import PASSWORD, register, sent_code

BODY = {"email": "anna@example.com", "password": PASSWORD, "last_name": "Петрова", "first_name": "Анна", "role": "teacher",
        "consent_pdn": True, "accept_terms": True}


@pytest.fixture
def no_email(monkeypatch):
    monkeypatch.setattr(settings, "email_codes", False)


async def test_register_and_login_without_codes(client, no_email):
    assert (await client.get("/auth/features")).json() == {"email_codes": False}
    reg = await client.post("/auth/register", json=BODY)
    assert reg.status_code == 201 and reg.json()["status"] == "authenticated" and "set-cookie" in reg.headers
    me = reg.json()["user"]
    assert me["email_verified"] is False and me["two_factor_method"] is None and me["email_codes"] is False

    login = await client.post("/auth/login", json={"identifier": "anna@example.com", "password": PASSWORD})
    assert login.json()["status"] == "authenticated"
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # Всё, что требует письма с кодом, — «скоро».
    assert (await client.post("/auth/password/forgot", json={"email": "anna@example.com"})).json()["error"]["code"] == "email_unavailable"
    assert (await client.put("/me/2fa", json={"enabled": True, "password": PASSWORD}, headers=auth)).status_code == 503
    assert (await client.post("/me/email", json={"email": "new@example.com", "password": PASSWORD}, headers=auth)).status_code == 503


async def test_confirm_email_after_mail_appears(client, monkeypatch):
    # Зарегистрировалась без почты, потом почту включили — подтверждает свой же адрес кодом.
    monkeypatch.setattr(settings, "email_codes", False)
    auth = {"Authorization": f"Bearer {(await client.post('/auth/register', json=BODY)).json()['access_token']}"}
    monkeypatch.setattr(settings, "email_codes", True)
    ch = (await client.post("/me/email", json={"email": "anna@example.com", "password": PASSWORD}, headers=auth)).json()
    code = await sent_code("anna@example.com", "email_change")
    done = (await client.post("/me/email/confirm", json={"challenge_id": ch["challenge_id"], "code": code}, headers=auth)).json()
    assert done["email_verified"] is True
    # Уже подтверждённый — «это ваш текущий email».
    again = await client.post("/me/email", json={"email": "anna@example.com", "password": PASSWORD}, headers=auth)
    assert again.json()["error"]["code"] == "same_email"


async def test_existing_two_factor_skipped(client, monkeypatch):
    # Зарегистрирован, пока почта была: вход с кодом включён. Почту выключили — пускаем без кода.
    await register(client, "petr@example.com")
    monkeypatch.setattr(settings, "email_codes", False)
    login = await client.post("/auth/login", json={"identifier": "petr@example.com", "password": PASSWORD})
    assert login.json()["status"] == "authenticated"
