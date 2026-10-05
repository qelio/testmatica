"""Личные ключи доступа (решение №41): выпуск, обмен на токен, отзыв."""

from testmatica_common.internal import INTERNAL_HEADER

from app.config import settings

from .conftest import events, login, register

H = {INTERNAL_HEADER: settings.internal_token}


def bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_api_key_lifecycle(client):
    await register(client, "teacher@example.com", role="teacher")
    await register(client, "pupil@example.com")
    teacher = bearer(await login(client, "teacher@example.com"))
    pupil = bearer(await login(client, "pupil@example.com"))

    # Ученику ключи не нужны — материалы создают педагоги.
    assert (await client.post("/me/api-keys", json={"name": "Claude"}, headers=pupil)).status_code == 403

    created = (await client.post("/me/api-keys", json={"name": "  Claude   Desktop "}, headers=teacher)).json()
    assert created["key"].startswith("tm_") and created["name"] == "Claude Desktop" and created["prefix"] == created["key"][:11]
    listed = (await client.get("/me/api-keys", headers=teacher)).json()
    assert [k["id"] for k in listed] == [created["id"]] and "key" not in listed[0]  # ключ показывается один раз
    assert (await events("identity.api_key.created"))[-1]["data"]["key_id"] == created["id"]

    # Обмен ключа на токен пользователя — для сервиса mcp, только по внутреннему токену.
    assert (await client.post("/internal/api-keys/exchange", json={"key": created["key"]})).status_code in (401, 403)
    ex = (await client.post("/internal/api-keys/exchange", json={"key": created["key"]}, headers=H)).json()
    me = (await client.get("/me", headers={"Authorization": f"Bearer {ex['access_token']}"})).json()
    assert me["email"] == "teacher@example.com" and "teacher" in me["roles"]
    assert (await client.get("/me/api-keys", headers=teacher)).json()[0]["last_used_at"] is not None
    bad = await client.post("/internal/api-keys/exchange", json={"key": "tm_wrongwrongwrong"}, headers=H)
    assert bad.json()["error"]["code"] == "invalid_api_key"

    # Отозванный ключ больше не работает; чужой ключ не отозвать.
    assert (await client.delete(f"/me/api-keys/{created['id']}", headers=pupil)).status_code == 404
    assert (await client.delete(f"/me/api-keys/{created['id']}", headers=teacher)).status_code == 204
    assert (await client.post("/internal/api-keys/exchange", json={"key": created["key"]}, headers=H)).status_code == 401
    assert (await client.get("/me/api-keys", headers=teacher)).json() == []
