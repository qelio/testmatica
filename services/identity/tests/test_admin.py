from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.api import admin as admin_api
from app.deps import db

from .conftest import PASSWORD, events, login, register


async def make_admin(client, email="boss@example.com") -> dict:
    await register(client, email, role="teacher")
    async with db.engine.begin() as conn:
        await conn.execute(text("INSERT INTO user_roles (user_id, role) SELECT id, 'admin' FROM users WHERE email = :e"), {"e": email})
    return {"Authorization": f"Bearer {(await login(client, email))['access_token']}"}


async def user_id(email: str) -> str:
    async with db.engine.connect() as conn:
        return str(await conn.scalar(text("SELECT id FROM users WHERE email = :e"), {"e": email}))


async def test_users_search_edit_roles(client):
    boss = await make_admin(client)
    await register(client, "anna@example.com")
    await register(client, "petr@example.com", role="teacher")
    anna, me = await user_id("anna@example.com"), await user_id("boss@example.com")

    # Не администратору — нельзя.
    student = {"Authorization": f"Bearer {(await login(client, 'anna@example.com'))['access_token']}"}
    assert (await client.get("/admin/users", headers=student)).status_code == 403

    page = (await client.get("/admin/users", params={"role": "teacher"}, headers=boss)).json()
    assert page["total"] == 2 and {u["email"] for u in page["items"]} == {"boss@example.com", "petr@example.com"}
    assert (await client.get("/admin/users", params={"q": "ANNA"}, headers=boss)).json()["items"][0]["id"] == anna

    edited = (await client.patch(f"/admin/users/{anna}", json={"name": {"last_name": " Смирнова", "first_name": "Анна "}, "login": "Anna.S"}, headers=boss)).json()
    assert edited["full_name"] == "Смирнова Анна" and edited["login"] == "anna.s"
    taken = await client.patch(f"/admin/users/{anna}", json={"email": "petr@example.com"}, headers=boss)
    assert taken.json()["error"]["code"] == "email_taken"
    assert (await events("identity.user.updated"))[-1]["data"]["full_name"] == "Смирнова Анна"

    roles = (await client.put(f"/admin/users/{anna}/roles", json={"roles": ["student", "moderator"]}, headers=boss)).json()
    assert roles["roles"] == ["moderator", "student"]
    changed = (await events("identity.user.roles_changed"))[0]["data"]
    assert changed["before"] == ["student"] and changed["after"] == ["moderator", "student"]
    assert (await client.put(f"/admin/users/{me}/roles", json={"roles": ["teacher"]}, headers=boss)).json()["error"]["code"] == "self_action"
    assert (await client.put(f"/admin/users/{anna}/roles", json={"roles": ["king"]}, headers=boss)).status_code == 422


async def test_ban_delete_restore_reset_and_anonymize(client):
    boss = await make_admin(client)
    await register(client, "anna@example.com")
    anna, me = await user_id("anna@example.com"), await user_id("boss@example.com")

    assert (await client.post(f"/admin/users/{me}/ban", json={"reason": "проверка"}, headers=boss)).json()["error"]["code"] == "self_action"
    banned = (await client.post(f"/admin/users/{anna}/ban", json={"reason": "Спам в чатах"}, headers=boss)).json()
    assert banned["status"] == "banned" and banned["status_reason"] == "Спам в чатах"
    resp = await client.post("/auth/login", json={"identifier": "anna@example.com", "password": PASSWORD})
    assert resp.json()["error"]["code"] == "account_banned"
    assert (await client.post(f"/admin/users/{anna}/unban", headers=boss)).json()["status"] == "active"

    temp = (await client.post(f"/admin/users/{anna}/reset-password", headers=boss)).json()["password"]
    assert (await client.post("/auth/login", json={"identifier": "anna@example.com", "password": PASSWORD})).status_code == 401
    assert (await client.post("/auth/login", json={"identifier": "anna@example.com", "password": temp})).status_code == 200

    deleted = (await client.post(f"/admin/users/{anna}/delete", json={"reason": "Просьба пользователя"}, headers=boss)).json()
    assert deleted["status"] == "deleted" and deleted["restore_until"]
    assert (await client.post(f"/admin/users/{anna}/restore", headers=boss)).json()["status"] == "active"

    # Через 30 дней после удаления — обезличивание, восстановить уже нельзя.
    await client.post(f"/admin/users/{anna}/delete", json={"reason": "Просьба пользователя"}, headers=boss)
    async with db.engine.begin() as conn:
        await conn.execute(text("UPDATE users SET deleted_at = :t WHERE id = :u"),
                           {"t": datetime.now(UTC) - timedelta(days=31), "u": anna})
    await admin_api.anonymize_deleted()
    gone = (await client.get(f"/admin/users/{anna}", headers=boss)).json()
    assert gone["full_name"] == "Удалённый пользователь" and gone["email"] is None and gone["login"].startswith("deleted-")
    assert (await client.post(f"/admin/users/{anna}/restore", headers=boss)).json()["error"]["code"] == "anonymized"
    assert (await events("identity.user.updated"))[-1]["data"]["full_name"] == "Удалённый пользователь"


async def test_stats_dau_mau(client):
    boss = await make_admin(client)
    await register(client, "anna@example.com")
    await login(client, "anna@example.com")
    s = (await client.get("/admin/stats", params={"days": 7}, headers=boss)).json()
    assert s["total"] == 2 and s["by_role"] == {"admin": 1, "student": 1, "teacher": 1}
    assert s["dau"] == 2 and s["mau"] == 2 and len(s["series"]) == 7
    assert s["series"][-1]["registrations"] == 2 and s["series"][-1]["active"] == 2


async def test_admin_changes_timezone(client):
    """Администратор меняет часовой пояс пользователя — по нему показывается расписание."""
    boss = await make_admin(client)
    await register(client, "pupil@example.com")
    pupil = await user_id("pupil@example.com")
    assert (await client.patch(f"/admin/users/{pupil}", json={"timezone": "Mars/Base"}, headers=boss)).status_code == 422
    ok = (await client.patch(f"/admin/users/{pupil}", json={"timezone": "Asia/Yekaterinburg"}, headers=boss)).json()
    assert ok["timezone"] == "Asia/Yekaterinburg"
    me = {"Authorization": f"Bearer {(await login(client, 'pupil@example.com'))['access_token']}"}
    assert (await client.get("/me", headers=me)).json()["timezone"] == "Asia/Yekaterinburg"
