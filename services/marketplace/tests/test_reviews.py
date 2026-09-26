from uuid import uuid4

from .conftest import bearer, decide, outbox, person
from .test_tutors import publish

STUDENT = ("student",)


async def review(client, tutor, student, rating=9, text="Отличный педагог, всё понятно объясняет."):
    return await client.put(f"/tutors/{tutor}/review", json={"rating": rating, "text": text}, headers=bearer(student, STUDENT))


async def test_review_moderation_and_rating(client, fakes):
    maria, olya, petya, stranger = uuid4(), uuid4(), uuid4(), uuid4()
    await person(maria, "Мария Иванова")
    await person(olya, "Оля Смирнова", STUDENT)
    await person(petya, "Петя Козлов", STUDENT)
    await publish(client, maria)
    fakes.link(maria, olya)
    fakes.link(maria, petya)

    # Отзыв — только от ученика этого педагога; себе нельзя.
    assert (await review(client, maria, stranger)).json()["error"]["code"] == "not_student"
    assert (await client.put(f"/tutors/{maria}/review", json={"rating": 5, "text": "Сам себя хвалю очень"},
                             headers=bearer(maria))).status_code == 403
    assert (await review(client, maria, olya, rating=11)).status_code == 422

    mine = (await review(client, maria, olya)).json()
    assert mine["status"] == "pending" and mine["tutor_name"] == "Мария Иванова"
    submitted = (await outbox("marketplace.review.submitted"))[0]["data"]
    assert submitted["rating"] == 9 and submitted["student_name"] == "Оля Смирнова"

    # До модерации отзыв не виден никому, кроме автора.
    page = (await client.get(f"/tutors/{maria}/reviews")).json()
    assert page["items"] == [] and page["rating"] is None and page["can_review"] is False
    own = (await client.get(f"/tutors/{maria}/reviews", headers=bearer(olya, STUDENT))).json()
    assert own["can_review"] and own["mine"]["status"] == "pending"

    await decide("review", mine["id"], "approve")
    petya_review = (await review(client, maria, petya, rating=6, text="Нормально, но иногда опаздывает.")).json()
    await decide("review", petya_review["id"], "approve")
    page = (await client.get(f"/tutors/{maria}/reviews")).json()
    assert page["rating"] == 7.5 and page["reviews_count"] == 2 and page["distribution"]["9"] == 1
    assert [r["student_name"] for r in page["items"]] == ["Петя Козлов", "Оля Смирнова"]
    card = (await client.get("/tutors", params={"min_rating": 7})).json()
    assert card["items"][0]["rating"] == 7.5
    assert (await client.get("/tutors", params={"min_rating": 8})).json()["total"] == 0

    # Правка — снова на проверку, до решения не учитывается в рейтинге.
    edited = (await review(client, maria, petya, rating=3, text="Передумал: часто опаздывает.")).json()
    assert edited["status"] == "pending"
    assert (await client.get(f"/tutors/{maria}/reviews")).json()["rating"] == 9.0
    await decide("review", edited["id"], "reject", "Оскорбительные формулировки")
    rejected = (await client.get("/reviews/mine", headers=bearer(petya, STUDENT))).json()[0]
    assert rejected["status"] == "rejected" and rejected["comment"] == "Оскорбительные формулировки"

    # Автор удаляет отзыв — рейтинг пересчитывается.
    assert (await client.delete(f"/reviews/{mine['id']}", headers=bearer(olya, STUDENT))).status_code == 204
    page = (await client.get(f"/tutors/{maria}/reviews")).json()
    assert page["rating"] is None and page["reviews_count"] == 0


async def test_reply_and_dispute(client, fakes):
    maria, olya = uuid4(), uuid4()
    await person(maria, "Мария Иванова")
    await person(olya, "Оля Смирнова", STUDENT)
    fakes.link(maria, olya)
    r = (await review(client, maria, olya, rating=2, text="Ничего не объясняет, только ругается.")).json()
    # Отвечать и спорить можно только по опубликованному отзыву.
    assert (await client.put(f"/reviews/{r['id']}/reply", json={"text": "Ответ"}, headers=bearer(maria))).status_code == 404
    await decide("review", r["id"], "approve")

    replied = (await client.put(f"/reviews/{r['id']}/reply", json={"text": "Жаль, что так вышло."}, headers=bearer(maria))).json()
    assert replied["reply_status"] == "pending" and replied["reply"] is None
    await decide("review_reply", r["id"], "approve")
    public = (await client.get(f"/tutors/{maria}/reviews")).json()["items"][0]
    assert public["reply"] == "Жаль, что так вышло."
    assert (await client.put(f"/reviews/{r['id']}/reply", json={"text": "x"}, headers=bearer(uuid4()))).status_code == 404

    disputed = (await client.post(f"/reviews/{r['id']}/dispute", json={"reason": "Ученица ни разу не была на занятии"},
                                  headers=bearer(maria))).json()
    assert disputed["dispute_status"] == "open" and disputed["dispute_id"]
    event = (await outbox("marketplace.review.disputed"))[0]["data"]
    assert event["dispute_id"] == disputed["dispute_id"] and event["reason"].startswith("Ученица")
    again = await client.post(f"/reviews/{r['id']}/dispute", json={"reason": "Ещё раз прошу разобраться"}, headers=bearer(maria))
    assert again.json()["error"]["code"] == "already_disputed"

    # Модератор признаёт спор — отзыв снят, рейтинг пересчитан, ученику нельзя его «воскресить» правкой.
    await decide("review_dispute", r["id"], "approve", "Отзыв не соответствует правилам")
    assert (await client.get(f"/tutors/{maria}/reviews")).json()["rating"] is None
    resolved = (await outbox("marketplace.review.dispute_resolved"))[0]["data"]
    assert resolved["upheld"] is True
    assert (await outbox("marketplace.review.removed"))[0]["data"]["comment"] == "Отзыв не соответствует правилам"
    assert (await review(client, maria, olya, rating=1)).json()["error"]["code"] == "review_removed"
    mine = (await client.get("/reviews/mine", headers=bearer(olya, STUDENT))).json()[0]
    assert mine["status"] == "removed"


async def test_dispute_dismissed_and_moderator_removal(client, fakes):
    maria, olya = uuid4(), uuid4()
    await person(maria, "Мария Иванова")
    fakes.link(maria, olya)
    r = (await review(client, maria, olya, rating=4)).json()
    await decide("review", r["id"], "approve")
    await client.post(f"/reviews/{r['id']}/dispute", json={"reason": "Не согласна с оценкой"}, headers=bearer(maria))
    await decide("review_dispute", r["id"], "reject", "Отзыв не нарушает правил")
    about = (await client.get("/me/reviews", headers=bearer(maria))).json()[0]
    assert about["dispute_status"] == "dismissed" and about["dispute_comment"] == "Отзыв не нарушает правил"
    assert (await client.get(f"/tutors/{maria}/reviews")).json()["rating"] == 4.0

    assert (await client.request("DELETE", f"/moderation/reviews/{r['id']}", json={"reason": "Спам"},
                                 headers=bearer(uuid4()))).status_code == 403
    gone = await client.request("DELETE", f"/moderation/reviews/{r['id']}", json={"reason": "Спам"},
                                headers=bearer(uuid4(), ("moderator",)))
    assert gone.status_code == 204
    assert (await client.get(f"/tutors/{maria}/reviews")).json()["reviews_count"] == 0
