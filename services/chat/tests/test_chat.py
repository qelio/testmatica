import asyncio
import json
from uuid import uuid4

from starlette.testclient import TestClient

from app import realtime
from app.deps import redis
from app.main import app

from .conftest import bearer, event, outbox, token


async def group_chat(client, user, roles=("student",)):
    convs = (await client.get("/conversations", headers=bearer(user, roles))).json()
    return next(c for c in convs if c["kind"] == "group")


async def send(client, conv_id, user, text, roles=("student",), announcement=False):
    return await client.post(
        f"/conversations/{conv_id}/messages", json={"text": text, "announcement": announcement}, headers=bearer(user, roles)
    )


T = ("teacher",)


async def test_group_chat_follows_group(client, school):
    teacher_chat = await group_chat(client, school["maria"], T)
    assert teacher_chat["title"] == "7А" and teacher_chat["my_role"] == "teacher"
    anya_chat = await group_chat(client, school["anya"])
    assert anya_chat["id"] == teacher_chat["id"] and anya_chat["my_role"] == "member"
    # Оля не в группе — группового чата у неё нет.
    assert (await client.get("/conversations", headers=bearer(school["olya"]))).json() == []

    await event("classroom.group.updated", group_id=school["gid"], teacher_id=school["maria"], title="8А")
    assert (await group_chat(client, school["anya"]))["title"] == "8А"

    await event("classroom.member.removed", group_id=school["gid"], teacher_id=school["maria"], student_id=school["petya"])
    assert (await client.get("/conversations", headers=bearer(school["petya"]))).json() == []
    assert (await client.get(f"/conversations/{anya_chat['id']}/messages", headers=bearer(school["petya"]))).status_code == 404


async def test_messages_unread_and_notifications(client, school):
    conv = await group_chat(client, school["anya"])
    assert (await send(client, conv["id"], school["anya"], "  Привет всем!  ")).status_code == 201
    assert (await send(client, conv["id"], school["anya"], "   ")).status_code == 422

    petya_view = await group_chat(client, school["petya"])
    assert petya_view["unread"] == 1
    assert petya_view["last_message"]["text"] == "Привет всем!"
    assert petya_view["last_message"]["author_name"] == "Аня"
    assert (await group_chat(client, school["anya"]))["unread"] == 0  # свои не считаются

    await client.post(f"/conversations/{conv['id']}/read", json={}, headers=bearer(school["petya"]))
    assert (await group_chat(client, school["petya"]))["unread"] == 0

    command = (await outbox("notification.inapp"))[0]["data"]
    assert sorted(command["user_ids"]) == sorted([str(school["maria"]), str(school["petya"])])
    assert command["title"] == "Новое сообщение: 7А" and command["body"] == "Аня: Привет всем!"
    assert command["coalesce_key"] == f"chat:{conv['id']}"
    # В аудит уходит событие без текста.
    audit_event = (await outbox("chat.message.created"))[0]["data"]
    assert "text" not in audit_event and audit_event["kind"] == "group"


async def test_announcement_is_teacher_only_and_pinned(client, school):
    conv = await group_chat(client, school["maria"], T)
    denied = await send(client, conv["id"], school["anya"], "Я объявляю", announcement=True)
    assert denied.status_code == 403
    ok = await send(client, conv["id"], school["maria"], "Контрольная в пятницу", T, announcement=True)
    assert ok.json()["is_announcement"] is True
    assert (await group_chat(client, school["anya"]))["pinned"]["text"] == "Контрольная в пятницу"
    assert (await outbox("notification.inapp"))[0]["data"]["title"] == "Объявление: 7А"

    assert (await client.delete(f"/conversations/{conv['id']}/pin", headers=bearer(school["anya"]))).status_code == 403
    assert (await client.delete(f"/conversations/{conv['id']}/pin", headers=bearer(school["maria"], T))).status_code == 204
    assert (await group_chat(client, school["anya"]))["pinned"] is None


async def test_direct_messages_follow_relations(client, school):
    contacts = (await client.get("/contacts", headers=bearer(school["anya"]))).json()
    assert [(c["full_name"], c["relation"]) for c in contacts] == [("Мария Ивановна", "педагог"), ("Петя", "одногруппник")]

    stranger = await client.post("/conversations/direct", json={"user_id": str(school["vasya"])}, headers=bearer(school["anya"]))
    assert stranger.status_code == 403
    # Оля и Аня у одного педагога, но не в одной группе — писать друг другу нельзя.
    not_classmates = await client.post("/conversations/direct", json={"user_id": str(school["olya"])}, headers=bearer(school["anya"]))
    assert not_classmates.status_code == 403

    dm = (await client.post("/conversations/direct", json={"user_id": str(school["petya"])}, headers=bearer(school["anya"]))).json()
    assert dm["title"] == "Петя" and dm["can_write"] is True
    again = (await client.post("/conversations/direct", json={"user_id": str(school["anya"])}, headers=bearer(school["petya"]))).json()
    assert again["id"] == dm["id"] and again["title"] == "Аня"

    # Пустой личный диалог в списке не показывается.
    assert [c["kind"] for c in (await client.get("/conversations", headers=bearer(school["petya"]))).json()] == ["group"]
    await send(client, dm["id"], school["anya"], "Что задали?")
    kinds = [c["kind"] for c in (await client.get("/conversations", headers=bearer(school["petya"]))).json()]
    assert kinds == ["direct", "group"]  # свежий чат — выше

    dm_command = (await outbox("notification.inapp"))[-1]["data"]
    assert dm_command["title"] == "Новое сообщение: Аня" and dm_command["body"] == "Что задали?"


async def test_unlinked_student_becomes_read_only(client, school):
    dm = (await client.post("/conversations/direct", json={"user_id": str(school["anya"])}, headers=bearer(school["maria"], T))).json()
    await send(client, dm["id"], school["maria"], "Как успехи?", T)
    await event("classroom.link.ended", link_id=uuid4(), teacher_id=school["maria"], student_id=school["anya"])

    anya_convs = (await client.get("/conversations", headers=bearer(school["anya"]))).json()
    # Из группового чата ушла, личная переписка осталась, но только для чтения.
    assert [(c["kind"], c["can_write"]) for c in anya_convs] == [("direct", False)]
    denied = await send(client, dm["id"], school["anya"], "Спасибо")
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "read_only"
    history = (await client.get(f"/conversations/{dm['id']}/messages", headers=bearer(school["anya"]))).json()
    assert [m["text"] for m in history] == ["Как успехи?"]


async def test_archived_group_is_read_only(client, school):
    conv = await group_chat(client, school["anya"])
    await event("classroom.group.archived", group_id=school["gid"], teacher_id=school["maria"])
    assert (await group_chat(client, school["anya"]))["can_write"] is False
    assert (await send(client, conv["id"], school["anya"], "Эй")).status_code == 403


async def test_history_pagination_and_delete(client, school):
    conv = await group_chat(client, school["anya"])
    for i in range(5):
        await send(client, conv["id"], school["anya"], f"сообщение {i}")
    page1 = (await client.get(f"/conversations/{conv['id']}/messages?limit=3", headers=bearer(school["petya"]))).json()
    assert [m["text"] for m in page1] == ["сообщение 4", "сообщение 3", "сообщение 2"]
    page2 = (
        await client.get(
            f"/conversations/{conv['id']}/messages", params={"limit": 3, "before": page1[-1]["created_at"]}, headers=bearer(school["petya"])
        )
    ).json()
    assert [m["text"] for m in page2] == ["сообщение 1", "сообщение 0"]

    assert (await client.delete(f"/messages/{page1[0]['id']}", headers=bearer(school["petya"]))).status_code == 404
    assert (await client.delete(f"/messages/{page1[0]['id']}", headers=bearer(school["anya"]))).status_code == 204
    latest = (await client.get(f"/conversations/{conv['id']}/messages?limit=1", headers=bearer(school["petya"]))).json()[0]
    assert latest["deleted"] is True and latest["text"] == "Сообщение удалено"


async def test_realtime_publish_reaches_user_channel():
    user = uuid4()
    pubsub = redis.pubsub()
    await pubsub.subscribe(realtime.channel(user))
    await pubsub.get_message(timeout=1)  # подтверждение подписки
    await realtime.publish([user], {"type": "message", "text": "Привет"})
    msg = None
    for _ in range(20):
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
        if msg:
            break
        await asyncio.sleep(0.05)
    await pubsub.aclose()
    assert json.loads(msg["data"]) == {"type": "message", "text": "Привет"}


def test_websocket_rejects_missing_or_bad_token():
    # Без «with»: не запускаем lifespan, чтобы не закрыть общие подключения к БД и Redis.
    tc = TestClient(app)
    with tc.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": "garbage"})
        closed = ws.receive()
    assert closed["type"] == "websocket.close" and closed["code"] == 4401
    with tc.websocket_connect("/ws") as ws:
        ws.send_json({"type": "hello", "token": token(uuid4())})
        assert ws.receive()["code"] == 4401


async def test_attachments(client, school, fake_media):
    conv = await group_chat(client, school["anya"])
    own = fake_media.add(school["anya"], "дз.pdf")
    foreign = fake_media.add(school["petya"], "чужое.pdf")

    only_file = await client.post(
        f"/conversations/{conv['id']}/messages", json={"attachment_ids": [own]}, headers=bearer(school["anya"])
    )
    assert only_file.status_code == 201, only_file.text
    att = only_file.json()["attachments"][0]
    assert (att["filename"], att["url"]) == ("дз.pdf", f"http://s3/{own}")
    assert (await outbox("notification.inapp"))[0]["data"]["body"] == "Аня: 📎 дз.pdf"

    stolen = await client.post(
        f"/conversations/{conv['id']}/messages", json={"text": "смотри", "attachment_ids": [foreign]}, headers=bearer(school["anya"])
    )
    assert stolen.status_code == 422
    empty = await client.post(f"/conversations/{conv['id']}/messages", json={}, headers=bearer(school["anya"]))
    assert empty.status_code == 422

    history = (await client.get(f"/conversations/{conv['id']}/messages", headers=bearer(school["petya"]))).json()
    assert history[0]["attachments"][0]["url"] == f"http://s3/{own}"

    fresh = await client.get(f"/conversations/{conv['id']}/attachments/{own}", headers=bearer(school["petya"]))
    assert fresh.json()["url"] == f"http://s3/{own}"
    # Посторонний не получит ссылку, даже зная id файла.
    assert (await client.get(f"/conversations/{conv['id']}/attachments/{own}", headers=bearer(school["olya"]))).status_code == 404
    assert (await client.get(f"/conversations/{conv['id']}/attachments/{uuid4()}", headers=bearer(school["petya"]))).status_code == 404


async def test_assessment_events_reach_teacher_and_student():
    """Начало и сдача теста, показ экрана — педагогу и ученику через WebSocket (страница теста обновляется сама)."""
    from testmatica_common.testing import make_envelope

    from app import live
    from app.deps import db

    teacher, pupil = uuid4(), uuid4()
    pubsub = redis.pubsub()
    await pubsub.subscribe(realtime.channel(teacher), realtime.channel(pupil))
    for _ in range(2):
        await pubsub.get_message(timeout=1)
    data = {"attempt_id": str(uuid4()), "assignment_id": str(uuid4()), "student_id": str(pupil), "teacher_id": str(teacher)}
    async with db.sessionmaker() as s:
        await live.on_assessment_event(make_envelope("assessment.attempt.graded", data | {"percent": 90}), s)  # не нужно
        await live.on_assessment_event(make_envelope("assessment.attempt.submitted", data | {"by_teacher": True}), s)
    got = []
    for _ in range(40):
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
        if msg:
            got.append((msg["channel"], json.loads(msg["data"])))
        if len(got) == 2:
            break
    await pubsub.aclose()
    assert {c for c, _ in got} == {realtime.channel(teacher), realtime.channel(pupil)}
    assert got[0][1]["type"] == "assignment" and got[0][1]["kind"] == "submitted" and got[0][1]["by_teacher"] is True
