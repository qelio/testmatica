import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from app.deps import db, media

from .conftest import PASSWORD, events, login, register, sent_code

H = {"X-Internal-Token": "dev-internal-token"}


@pytest.fixture
def files():
    """media: файлы по владельцу; claim проверяет, что файл свой."""
    store: dict[str, str] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if request.url.path.endswith("/claim"):
            fid = body["file_ids"][0]
            if store.get(fid) != body["owner_id"]:
                return httpx.Response(422, json={"error": {"code": "invalid_attachment", "message": "Файл не найден"}})
            return httpx.Response(200, json=[{"id": fid}])
        return httpx.Response(200, json={i: {"id": i, "url": f"http://s3/{i}"} for i in body["file_ids"] if i in store})

    media.transport = httpx.MockTransport(handle)
    return store


def auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_profile_avatar_password(client, files):
    await register(client, "anna@example.com")
    me = auth(await login(client, "anna@example.com"))
    info = (await client.get("/me", headers=me)).json()
    assert info["two_factor_method"] == "email" and info["email_verified"] and info["avatar_url"] is None

    name = {"last_name": "  Петрова ", "first_name": "Анна", "middle_name": "Сергеевна"}
    updated = (await client.patch("/me", json={"name": name, "timezone": "Asia/Yekaterinburg"}, headers=me)).json()
    assert updated["full_name"] == "Петрова Анна Сергеевна" and updated["timezone"] == "Asia/Yekaterinburg"
    assert (updated["last_name"], updated["first_name"], updated["middle_name"]) == ("Петрова", "Анна", "Сергеевна")
    assert (await events("identity.user.updated"))[-1]["data"]["full_name"] == "Петрова Анна Сергеевна"
    assert (await client.patch("/me", json={"timezone": "Mars/Base"}, headers=me)).status_code == 422

    fid = str(uuid4())
    files[fid] = info["id"]
    with_photo = (await client.put("/me/avatar", json={"file_id": fid}, headers=me)).json()
    assert with_photo["avatar_url"] == f"http://s3/{fid}"
    foreign = str(uuid4())
    files[foreign] = str(uuid4())
    assert (await client.put("/me/avatar", json={"file_id": foreign}, headers=me)).status_code == 422
    assert (await events("identity.user.avatar_changed"))[-1]["data"] == {"user_id": info["id"], "file_id": fid}
    assert (await client.put("/me/avatar", json={"file_id": None}, headers=me)).json()["avatar_url"] is None

    # Фото из анкеты репетитора (marketplace) — то же фото профиля.
    other = str(uuid4())
    files[other] = info["id"]
    assert (await client.post(f"/internal/users/{info['id']}/avatar", json={"file_id": other}, headers=H)).status_code == 204
    assert (await client.get("/me", headers=me)).json()["avatar_url"] == f"http://s3/{other}"

    wrong = await client.post("/me/password", json={"current_password": "nope", "new_password": "new-secret-2"}, headers=me)
    assert wrong.json()["error"]["code"] == "wrong_password"
    ok = await client.post("/me/password", json={"current_password": PASSWORD, "new_password": "new-secret-2"}, headers=me)
    assert ok.status_code == 204 and "set-cookie" in ok.headers  # текущее устройство получает новую сессию
    assert (await client.post("/auth/login", json={"identifier": "anna@example.com", "password": PASSWORD})).status_code == 401


async def test_change_email_with_code(client, files):
    await register(client, "anna@example.com")
    await register(client, "petr@example.com")
    me = auth(await login(client, "anna@example.com"))
    assert (await client.post("/me/email", json={"email": "petr@example.com", "password": PASSWORD}, headers=me)).json()["error"]["code"] == "email_taken"
    ch = (await client.post("/me/email", json={"email": "Anna.New@example.com", "password": PASSWORD}, headers=me)).json()
    code = await sent_code("anna.new@example.com", "email_change")  # код — на новый адрес
    bad = await client.post("/me/email/confirm", json={"challenge_id": ch["challenge_id"], "code": "000000"}, headers=me)
    assert bad.status_code == 400
    done = (await client.post("/me/email/confirm", json={"challenge_id": ch["challenge_id"], "code": code}, headers=me)).json()
    assert done["email"] == "anna.new@example.com"
    resp = await client.post("/auth/login", json={"identifier": "anna.new@example.com", "password": PASSWORD})
    assert resp.json()["status"] == "2fa_required"


async def test_two_factor_toggle_and_managed_student(client, files):
    await register(client, "anna@example.com")
    me = auth(await login(client, "anna@example.com"))
    off = (await client.put("/me/2fa", json={"enabled": False, "password": PASSWORD}, headers=me)).json()
    assert off["two_factor_method"] is None
    direct = await client.post("/auth/login", json={"identifier": "anna@example.com", "password": PASSWORD})
    assert direct.json()["status"] == "authenticated"  # без кода
    assert (await client.put("/me/2fa", json={"enabled": True, "password": PASSWORD}, headers=me)).json()["two_factor_method"] == "email"

    # Модератору выключить нельзя.
    async with db.engine.begin() as conn:
        await conn.execute(text("INSERT INTO user_roles (user_id, role) SELECT id, 'moderator' FROM users WHERE email = 'anna@example.com'"))
    mod = auth(await login(client, "anna@example.com"))
    assert (await client.get("/me", headers=mod)).json()["two_factor_required"] is True
    denied = await client.put("/me/2fa", json={"enabled": False, "password": PASSWORD}, headers=mod)
    assert denied.json()["error"]["code"] == "two_factor_required"

    # Ученик без email: включить нельзя, пока не добавит адрес; добавил — вход с кодом включается сам (решение №6).
    creds = (await client.post("/internal/managed-students", json={"teacher_id": str(uuid4()), "last_name": "Иванов", "first_name": "Петя"}, headers=H)).json()
    resp = await client.post("/auth/login", json={"identifier": creds["login"], "password": creds["password"]})
    pupil = auth(resp.json())
    assert (await client.get("/me", headers=pupil)).json()["managed"] is True
    need = await client.put("/me/2fa", json={"enabled": True, "password": creds["password"]}, headers=pupil)
    assert need.json()["error"]["code"] == "email_required"
    ch = (await client.post("/me/email", json={"email": "petya@example.com", "password": creds["password"]}, headers=pupil)).json()
    code = await sent_code("petya@example.com", "email_change")
    done = (await client.post("/me/email/confirm", json={"challenge_id": ch["challenge_id"], "code": code}, headers=pupil)).json()
    assert done["email"] == "petya@example.com" and done["two_factor_method"] == "email"


async def test_consents_on_first_login(client, files):
    # Зарегистрировался сам — согласия даны при регистрации (две отдельные галочки).
    await register(client, "anna@example.com")
    me = auth(await login(client, "anna@example.com"))
    assert (await client.get("/me", headers=me)).json()["consent_required"] is False
    no_terms = await client.post("/auth/register", json={"email": "b@example.com", "password": PASSWORD, "last_name": "Б", "first_name": "Б",
                                                         "role": "student", "consent_pdn": True, "accept_terms": False})
    assert no_terms.status_code == 422

    # Ученик, созданный педагогом, — окно согласия при первом входе; без галочек дальше нельзя.
    creds = (await client.post("/internal/managed-students", json={"teacher_id": str(uuid4()), "last_name": "Иванов", "first_name": "Петя"}, headers=H)).json()
    pupil = auth((await client.post("/auth/login", json={"identifier": creds["login"], "password": creds["password"]})).json())
    assert (await client.get("/me", headers=pupil)).json()["consent_required"] is True
    bad = await client.post("/me/consents", json={"accept_terms": True, "consent_pdn": False}, headers=pupil)
    assert bad.status_code == 422
    ok = await client.post("/me/consents", json={"accept_terms": True, "consent_pdn": True, "by_representative": True},
                           headers={**pupil, "User-Agent": "Test/1.0"})
    assert ok.json()["consent_required"] is False
    async with db.engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT type, source, by_representative, user_agent FROM consents c JOIN users u ON u.id = c.user_id WHERE u.login = :l"
        ), {"l": creds["login"]})).all()
    assert {r.type for r in rows} == {"terms", "pdn"} and all(r.source == "first_login" and r.by_representative for r in rows)
    assert rows[0].user_agent == "Test/1.0"
    assert (await events("identity.user.consented"))[-1]["data"]["source"] == "first_login"
