"""Показ экрана педагога на доске по коду (решение №53)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import update

from app.api import board as board_api
from app.deps import db
from app.models import BoardSession

from .conftest import bearer, webhook


async def test_board_pairing_flow(client, lk):
    teacher = uuid4()
    created = (await client.post("/board/sessions")).json()  # доска — без входа
    assert len(created["code"]) == 6 and created["code"].isdigit()
    url = f"/board/sessions/{created['id']}"
    secret = {"secret": created["secret"]}
    assert (await client.get(url, params=secret)).json()["status"] == "waiting"
    assert (await client.get(url, params={"secret": "чужой-секрет-доски"})).status_code == 404

    # Ученик показывать не может; педагог вводит код — получает пропуск только для показа.
    assert (await client.post("/board/pair", json={"code": created["code"]}, headers=bearer(uuid4()))).status_code == 403
    paired = (await client.post("/board/pair", json={"code": created["code"]}, headers=bearer(teacher, ("teacher",)))).json()
    room = f"board-{created['id']}"
    assert paired["token"] == f"board-token-t-{teacher}" and lk.rooms[room] == 4
    assert lk.tokens[-1]["presenter"] is True
    # Код одноразовый.
    again = await client.post("/board/pair", json={"code": created["code"]}, headers=bearer(uuid4(), ("teacher",)))
    assert again.status_code == 404 and again.json()["error"]["code"] == "board_code_invalid"

    live = (await client.get(url, params=secret)).json()
    assert (live["status"], live["token"], live["url"]) == ("live", f"board-token-b-{created['id']}", "ws://lk.test")
    assert lk.tokens[-1]["presenter"] is False  # доска только смотрит

    # Педагог закрыл вкладку — показ завершён; доска берёт новый код.
    await webhook("participant_left", room, identity=f"t-{teacher}")
    assert (await client.get(url, params=secret)).json()["status"] == "ended"


async def test_board_stop_expire_and_bruteforce(client, lk):
    teacher = uuid4()
    created = (await client.post("/board/sessions")).json()
    paired = (await client.post("/board/pair", json={"code": created["code"]}, headers=bearer(teacher, ("teacher",)))).json()
    assert (await client.post(f"/board/sessions/{paired['id']}/stop", headers=bearer(uuid4(), ("teacher",)))).status_code == 404
    assert (await client.post(f"/board/sessions/{paired['id']}/stop", headers=bearer(teacher, ("teacher",)))).status_code == 204
    assert lk.deleted == [f"board-{created['id']}"]

    # Код истёк — не подходит.
    old = (await client.post("/board/sessions")).json()
    async with db.sessionmaker() as s, s.begin():
        await s.execute(update(BoardSession).where(BoardSession.id == old["id"]).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    assert (await client.get(f"/board/sessions/{old['id']}", params={"secret": old["secret"]})).json()["status"] == "expired"
    assert (await client.post("/board/pair", json={"code": old["code"]}, headers=bearer(teacher, ("teacher",)))).status_code == 404

    # Перебор кодов: после 10 неверных — пауза.
    guesser = uuid4()
    board_api._failures.clear()
    for _ in range(10):
        await client.post("/board/pair", json={"code": "000000"}, headers=bearer(guesser, ("teacher",)))
    fresh = (await client.post("/board/sessions")).json()
    blocked = await client.post("/board/pair", json={"code": fresh["code"]}, headers=bearer(guesser, ("teacher",)))
    assert blocked.status_code == 429
