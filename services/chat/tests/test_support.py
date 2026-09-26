from uuid import uuid4

from app import support
from app.deps import db
from testmatica_common.testing import make_envelope

from .conftest import bearer, person


async def review_event(type_: str, actor=None, **data) -> None:
    async with db.sessionmaker() as s, s.begin():
        await support.on_review_event(
            make_envelope(type_, {k: str(v) if not isinstance(v, (int, bool)) else v for k, v in data.items()}, actor_id=actor), s
        )


async def test_review_dispute_opens_support_chat(client):
    tutor = await person("Мария Иванова", ("teacher",))
    moderator = await person("Модератор Иван", ("moderator",))
    student = await person("Оля Смирнова")
    dispute = uuid4()
    base = {"review_id": uuid4(), "tutor_id": tutor, "student_id": student, "tutor_name": "Мария Иванова",
            "student_name": "Оля Смирнова", "rating": 2, "dispute_id": dispute}
    await review_event("marketplace.review.disputed", tutor, **base, text="Ничего не объясняет", reason="Не была на занятиях")
    await review_event("marketplace.review.disputed", tutor, **base, text="Ничего не объясняет", reason="Повтор")  # без дубля

    [conv] = (await client.get("/conversations", headers=bearer(tutor, ("teacher",)))).json()
    assert conv["id"] == str(dispute) and conv["kind"] == "support" and conv["title"] == "Спор по отзыву · Мария Иванова"
    assert conv["can_write"] is True
    [mod_conv] = (await client.get("/conversations", headers=bearer(moderator, ("moderator",)))).json()
    assert mod_conv["id"] == str(dispute)
    assert (await client.get("/conversations", headers=bearer(student))).json() == []  # ученик спор не видит

    reply = await client.post(f"/conversations/{dispute}/messages", json={"text": "Проверим журнал посещений"},
                              headers=bearer(moderator, ("moderator",)))
    assert reply.status_code == 201
    await review_event("marketplace.review.dispute_resolved", moderator, **base, upheld=True, comment="Ученица не занималась")
    msgs = (await client.get(f"/conversations/{dispute}/messages", headers=bearer(tutor, ("teacher",)))).json()
    texts = [m["text"] for m in reversed(msgs)]
    assert texts[0].startswith("Педагог оспаривает отзыв ученика Оля Смирнова (оценка 2/10)")
    assert texts[-1] == "✅ Модератор удалил отзыв. Комментарий: Ученица не занималась"
