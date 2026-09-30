import httpx
import pytest

from app.deps import billing, plans

from .conftest import bearer, outbox, person

SUBSCRIBERS: set[str] = set()


@pytest.fixture(autouse=True)
def fake_billing():
    """billing: тариф «Базовый» — у педагогов из SUBSCRIBERS."""
    SUBSCRIBERS.clear()
    plans.reset()

    def handle(request: httpx.Request) -> httpx.Response:
        import json

        ids = json.loads(request.content)["user_ids"]
        return httpx.Response(200, json={u: "basic" if u in SUBSCRIBERS else "free" for u in ids})

    billing.transport = httpx.MockTransport(handle)


async def test_ticket_lifecycle(client):
    olya = await person("Оля Смирнова")
    mod = await person("Модератор Иван", ("moderator",))
    admin = await person("Админ Анна", ("admin",))
    O, M, A = bearer(olya), bearer(mod, ("moderator",)), bearer(admin, ("admin",))

    bad = await client.post("/support/tickets", json={"category": "nope", "subject": "Тема", "text": "Текст"}, headers=O)
    assert bad.status_code == 422
    t = (await client.post("/support/tickets", json={"category": "account", "subject": "Не приходит код",
                                                      "text": "Код на почту не приходит"}, headers=O)).json()
    assert t["status"] == "open" and not t["priority"] and t["requester_name"] == "Оля Смирнова"
    assert (await outbox("chat.ticket.created"))[0]["data"]["category"] == "account"
    # Переписка — обычный чат: первое сообщение уже там, поддержка — участники.
    msgs = (await client.get(f"/conversations/{t['id']}/messages", headers=M)).json()
    assert [m["text"] for m in msgs] == ["Код на почту не приходит"]
    assert [x["id"] for x in (await client.get("/support/tickets", headers=O)).json()] == [t["id"]]

    # Очередь поддержки; ученику недоступна.
    assert (await client.get("/support/queue", headers=O)).status_code == 403
    q = (await client.get("/support/queue", headers=M)).json()
    assert [x["id"] for x in q] == [t["id"]] and q[0]["unread"] == 1
    assert (await client.get("/support/queue/counts", headers=M)).json() == {"open": 1, "mine_open": 0}

    # Ответ поддержки → «ответили», обращение закрепляется за ответившим.
    await client.post(f"/conversations/{t['id']}/messages", json={"text": "Проверьте папку «Спам»"}, headers=M)
    got = (await client.get(f"/support/tickets/{t['id']}", headers=O)).json()
    assert got["status"] == "answered" and got["assignee_name"] == "Модератор Иван" and got["unread"] == 1
    # Админ берёт себе — служебное сообщение в переписке.
    assert (await client.post(f"/support/tickets/{t['id']}/assign", headers=A)).json()["assignee_name"] == "Админ Анна"

    # Автор закрыл, потом написал снова — обращение открылось.
    assert (await client.post(f"/support/tickets/{t['id']}/close", headers=O)).json()["status"] == "closed"
    assert (await client.get("/support/queue", params={"status": "closed"}, headers=M)).json()[0]["id"] == t["id"]
    await client.post(f"/conversations/{t['id']}/messages", json={"text": "Всё-таки не пришёл"}, headers=O)
    assert (await client.get(f"/support/tickets/{t['id']}", headers=O)).json()["status"] == "open"

    # Чужое обращение не видно.
    vasya = await person("Вася")
    assert (await client.get(f"/support/tickets/{t['id']}", headers=bearer(vasya))).status_code == 404
    # Поддержка обращений не создаёт.
    assert (await client.post("/support/tickets", json={"category": "other", "subject": "Тема", "text": "x"}, headers=M)).status_code == 403


async def test_subscribers_first_and_late_staff(client):
    free = await person("Педагог без подписки", ("teacher",))
    paid = await person("Педагог с подпиской", ("teacher",))
    SUBSCRIBERS.add(str(paid))
    body = {"category": "payments", "subject": "Вопрос по тарифу", "text": "Как продлить?"}
    first = (await client.post("/support/tickets", json=body, headers=bearer(free, ("teacher",)))).json()
    second = (await client.post("/support/tickets", json=body, headers=bearer(paid, ("teacher",)))).json()
    assert second["priority"] and not first["priority"]

    # Модератор появился после создания обращений: видит очередь и становится участником, открыв обращение.
    late = await person("Новый модератор", ("moderator",))
    L = bearer(late, ("moderator",))
    assert [x["id"] for x in (await client.get("/support/queue", headers=L)).json()] == [second["id"], first["id"]]
    await client.get(f"/support/tickets/{first['id']}", headers=L)
    reply = await client.post(f"/conversations/{first['id']}/messages", json={"text": "Отвечаю"}, headers=L)
    assert reply.status_code == 201
