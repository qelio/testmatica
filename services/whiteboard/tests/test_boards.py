from uuid import uuid4

from .conftest import bearer, person, student


def stroke(**data):
    return {"id": str(uuid4()), "kind": "stroke", "z": 1, "data": {"tool": "pen", "color": "#000", "size": 2, "points": [[0, 0, 0.5], [10, 10, 0.5]]} | data}


async def test_lesson_board_and_student_access(client, world):
    """Доска занятия (решение №60): одна на занятие, видна его ученикам; доступ — закрыт, чтение или правка."""
    maria, olya, petya, stranger = await person("Иванова Мария"), uuid4(), uuid4(), uuid4()
    group = world.group(maria, [olya, petya])
    lesson = world.lesson(maria, [olya, petya], group_id=group)

    # Ученик до открытия доски педагогом — её нет; чужой педагог не может открыть доску чужого занятия.
    assert (await client.get(f"/lessons/{lesson}/board", headers=student(olya))).status_code == 404
    assert (await client.post(f"/lessons/{lesson}/board", headers=bearer(stranger))).status_code == 404
    board = (await client.post(f"/lessons/{lesson}/board", headers=bearer(maria))).json()
    assert board["title"] == "Алгебра — 21.10.2026: Дроби" and board["target_title"] == "7А" and board["access"] == "read"
    again = (await client.post(f"/lessons/{lesson}/board", headers=bearer(maria))).json()
    assert again["id"] == board["id"]  # повторно — та же доска
    url = f"/boards/{board['id']}"

    item = stroke()
    assert (await client.post(f"{url}/ops", json={"upsert": [item]}, headers=bearer(maria))).status_code == 204
    # Ученик видит доску (только чтение), рисовать не может; посторонний не видит.
    seen = (await client.get(f"/lessons/{lesson}/board", headers=student(olya))).json()
    assert seen["role"] == "read" and seen["owner_name"] == "Иванова Мария"
    full = (await client.get(url, headers=student(olya))).json()
    assert [i["id"] for i in full["items"]] == [item["id"]]
    assert (await client.post(f"{url}/ops", json={"upsert": [stroke()]}, headers=student(olya))).status_code == 403
    assert (await client.get(url, headers=student(stranger))).status_code == 404
    assert (await client.patch(url, json={"access": "edit"}, headers=student(olya))).status_code in (403, 404)

    # Правка — ученик рисует и удаляет; закрыли — доска пропала из его списка.
    await client.patch(url, json={"access": "edit", "paper_style": "grid", "paper_color": "chalk"}, headers=bearer(maria))
    own = stroke(color="#f00")
    assert (await client.post(f"{url}/ops", json={"upsert": [own], "delete": [item["id"]]}, headers=student(olya))).status_code == 204
    full = (await client.get(url, headers=bearer(maria))).json()
    assert [(i["id"], i["author_id"]) for i in full["items"]] == [(own["id"], str(olya))]
    assert (full["paper_style"], full["paper_color"]) == ("grid", "chalk")
    assert [b["id"] for b in (await client.get("/boards", headers=student(petya))).json()] == [board["id"]]
    await client.patch(url, json={"access": "none"}, headers=bearer(maria))
    assert (await client.get(url, headers=student(olya))).status_code == 404
    assert (await client.get("/boards", headers=student(petya))).json() == []

    assert (await client.delete(url, headers=bearer(maria))).status_code == 204
    assert (await client.get("/boards", headers=bearer(maria))).json() == []


async def test_free_board_targets_and_limits(client, world):
    """Свободная доска: никому, классу или ученику; состав класса обновляется; объект чужой доски не перезаписать."""
    maria, olya, vasya = uuid4(), uuid4(), uuid4()
    petya = await person("Петров Петя")
    group = world.group(maria, [olya])
    world.links.add((str(maria), str(petya)))

    board = (await client.post("/boards", json={"title": "  Черновик  "}, headers=bearer(maria))).json()
    assert board["title"] == "Черновик" and board["target_title"] is None and board["lesson_id"] is None
    url = f"/boards/{board['id']}"
    assert (await client.get(url, headers=student(olya))).status_code == 404
    assert (await client.post("/boards", json={"title": "Ч", "group_id": str(uuid4())}, headers=bearer(maria))).status_code == 404

    await client.patch(url, json={"target": {"group_id": str(group)}}, headers=bearer(maria))
    assert (await client.get(url, headers=student(olya))).status_code == 200
    world.groups[str(group)]["member_ids"].append(str(vasya))  # в класс добавили ученика
    await client.get(url, headers=bearer(maria))
    assert (await client.get(url, headers=student(vasya))).status_code == 200
    out = (await client.patch(url, json={"target": {"student_id": str(petya)}}, headers=bearer(maria))).json()
    assert out["target_title"] == "Петров Петя"
    assert (await client.get(url, headers=student(olya))).status_code == 404

    lesson = world.lesson(maria, [olya])
    await client.post(f"/lessons/{lesson}/board", headers=bearer(maria))
    kinds = {k: [b["lesson_id"] is not None for b in (await client.get("/boards", params={"kind": k}, headers=bearer(maria))).json()]
             for k in ("all", "lesson", "free")}
    assert kinds == {"all": [True, False], "lesson": [True], "free": [False]}

    # Тот же id объекта на другой доске не перезаписывает чужой объект.
    other = (await client.post("/boards", json={"title": "Другая"}, headers=bearer(petya))).json()
    item = stroke()
    await client.post(f"{url}/ops", json={"upsert": [item]}, headers=bearer(maria))
    await client.post(f"/boards/{other['id']}/ops", json={"upsert": [item | {"data": {"hacked": True}}]}, headers=bearer(petya))
    [kept] = (await client.get(url, headers=bearer(maria))).json()["items"]
    assert "hacked" not in kept["data"]
    big = await client.post(f"{url}/ops", json={"upsert": [stroke(points=[[i, i, 0.5] for i in range(20000)])]}, headers=bearer(maria))
    assert big.json()["error"]["code"] == "item_too_large"


def test_websocket_rejects_bad_token():
    """Без токена или с чужим — соединение закрывается сразу (4401)."""
    from starlette.testclient import TestClient

    from app.main import app

    with TestClient(app).websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": "bad", "board_id": str(uuid4())})
        closed = ws.receive()
    assert closed["type"] == "websocket.close" and closed["code"] == 4401
