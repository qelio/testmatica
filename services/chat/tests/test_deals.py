from uuid import uuid4

from app import deals
from app.deps import db
from testmatica_common.testing import make_envelope

from .conftest import bearer, person


async def market(type_: str, actor=None, **data) -> None:
    async with db.sessionmaker() as s, s.begin():
        await deals.on_marketplace_event(make_envelope(type_, {k: str(v) if not isinstance(v, (int, bool)) else v for k, v in data.items()},
                                                       actor_id=actor), s)


async def test_negotiation_chat_without_link(client):
    tutor = await person("Мария Иванова", ("teacher",))
    pupil = await person("Оля Смирнова")
    stranger = await person("Петя")
    rid = uuid4()
    base = {"response_id": rid, "request_id": uuid4(), "student_id": pupil, "tutor_id": tutor, "subject": "Математика",
            "price": 1200, "duration_min": 60}
    await market("marketplace.response.created", tutor, **base, direct=False, message="Здравствуйте! Готова помочь.")
    await market("marketplace.response.created", tutor, **base, direct=False, message="")  # повтор события — без дубля чата

    convs = (await client.get("/conversations", headers=bearer(pupil))).json()
    [conv] = convs
    assert conv["id"] == str(rid) and conv["kind"] == "deal" and conv["title"] == "Мария Иванова · заявка: Математика"
    assert conv["can_write"] is True  # привязки нет, но переговоры идут
    msgs = (await client.get(f"/conversations/{rid}/messages", headers=bearer(pupil))).json()
    texts = [(m["text"], m["is_system"]) for m in reversed(msgs)]
    assert texts[0] == ("Репетитор откликнулся на заявку: Математика. Цена — 1 200 ₽ за 60 мин.", True)
    assert ("Здравствуйте! Готова помочь.", False) in texts

    sent = await client.post(f"/conversations/{rid}/messages", json={"text": "Можно по вечерам?"}, headers=bearer(pupil))
    assert sent.status_code == 201
    assert (await client.get(f"/conversations/{rid}/messages", headers=bearer(stranger))).status_code == 404

    await market("marketplace.response.price_proposed", tutor, **base | {"price": 1500}, by="tutor")
    await market("marketplace.deal.agreed", pupil, **base | {"price": 1500})
    last = (await client.get(f"/conversations/{rid}/messages", headers=bearer(tutor))).json()
    assert last[1]["text"] == "Репетитор предлагает цену: 1 500 ₽ за 60 мин."
    assert last[0]["text"].startswith("✅ Договорились: 1 500 ₽ за 60 мин.") and last[0]["is_system"]
