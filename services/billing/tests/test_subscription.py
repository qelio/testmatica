from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app import subscriptions

from .conftest import INTERNAL, bearer, outbox, sql


async def buy(client, user, card="4242", auto_renew=True):
    pay = (await client.post("/subscription/checkout", json={"auto_renew": auto_renew, "accept_offer": True}, headers=bearer(user))).json()
    result = await client.post(f"/fake-provider/payments/{pay['id']}", json={"outcome": "success", "card_last4": card},
                               headers=bearer(user))
    return pay, result.json()


def test_add_month():
    assert subscriptions.add_month(datetime(2026, 1, 31, tzinfo=UTC)) == datetime(2026, 2, 28, tzinfo=UTC)
    assert subscriptions.add_month(datetime(2026, 12, 15, tzinfo=UTC)) == datetime(2027, 1, 15, tzinfo=UTC)


async def test_checkout_with_fake_provider(client):
    maria, student = uuid4(), uuid4()
    state = (await client.get("/subscription", headers=bearer(maria))).json()
    assert state["plan"] == "free" and state["price_rub"] == 490 and state["pending_payment"] is None
    assert (await client.post("/subscription/checkout", json={"accept_offer": True}, headers=bearer(student, ("student",)))).status_code == 403

    no_offer = await client.post("/subscription/checkout", json={"auto_renew": True, "accept_offer": False}, headers=bearer(maria))
    assert no_offer.status_code == 422
    pay = (await client.post("/subscription/checkout", json={"auto_renew": True, "accept_offer": True}, headers=bearer(maria))).json()
    assert pay["amount_rub"] == 490 and pay["status"] == "pending" and pay["confirmation_url"].endswith(f"/dashboard/pay/{pay['id']}")
    again = (await client.post("/subscription/checkout", json={"auto_renew": True, "accept_offer": True}, headers=bearer(maria))).json()
    assert again["id"] == pay["id"]  # незавершённый платёж продолжается, а не дублируется
    assert (await client.get("/subscription", headers=bearer(maria))).json()["pending_payment"]["id"] == pay["id"]
    # Чужой платёж подтвердить нельзя.
    assert (await client.post(f"/fake-provider/payments/{pay['id']}", json={"outcome": "success"},
                              headers=bearer(uuid4()))).status_code == 404

    done = (await client.post(f"/fake-provider/payments/{pay['id']}", json={"outcome": "success", "card_last4": "4242"},
                              headers=bearer(maria))).json()
    assert done["status"] == "succeeded" and done["confirmation_url"] is None
    state = (await client.get("/subscription", headers=bearer(maria))).json()
    assert state["plan"] == "basic" and state["auto_renew"] and state["payment_method_title"] == "Карта •• 4242"
    end = datetime.fromisoformat(state["period_end"])
    assert timedelta(days=27) < end - datetime.now(UTC) < timedelta(days=32)
    changed = (await outbox("billing.subscription.changed"))[0]["data"]
    assert changed["plan"] == "basic" and changed["reason"] == "purchased"
    assert (await client.post(f"/fake-provider/payments/{pay['id']}", json={"outcome": "success"},
                              headers=bearer(maria))).json()["error"]["code"] == "payment_finished"

    # Досрочное продление — от конца текущего периода.
    await buy(client, maria)
    later = datetime.fromisoformat((await client.get("/subscription", headers=bearer(maria))).json()["period_end"])
    assert later == subscriptions.add_month(end)

    plans = await client.post("/internal/plans", json={"user_ids": [str(maria), str(student)]}, headers=INTERNAL)
    assert plans.json() == {str(maria): "basic", str(student): "free"}
    assert (await client.post("/internal/plans", json={"user_ids": []})).status_code == 403
    history = (await client.get("/payments", headers=bearer(maria))).json()
    assert [p["status"] for p in history] == ["succeeded", "succeeded"]


async def test_declined_and_cancelled(client):
    maria = uuid4()
    _, declined = await buy(client, maria, card="0002")
    assert declined["status"] == "canceled" and declined["error"] == "Банк отклонил оплату"
    pay = (await client.post("/subscription/checkout", json={"auto_renew": False, "accept_offer": True}, headers=bearer(maria))).json()
    cancelled = (await client.post(f"/fake-provider/payments/{pay['id']}", json={"outcome": "cancel"}, headers=bearer(maria))).json()
    assert cancelled["status"] == "canceled"
    assert (await client.get("/subscription", headers=bearer(maria))).json()["plan"] == "free"
    assert len(await outbox("billing.payment.failed")) == 2

    # Без галочки автопродления карта не сохраняется — включить автопродление нельзя.
    await buy(client, maria, auto_renew=False)
    state = (await client.get("/subscription", headers=bearer(maria))).json()
    assert state["plan"] == "basic" and not state["auto_renew"] and state["payment_method_title"] is None
    on = await client.put("/subscription/auto-renew", json={"enabled": True}, headers=bearer(maria))
    assert on.json()["error"]["code"] == "no_payment_method"


async def test_renewal_reminder_and_expiry(client):
    ok, failing, manual = uuid4(), uuid4(), uuid4()
    await buy(client, ok)
    await buy(client, failing)
    await buy(client, manual, auto_renew=False)
    soon = datetime.now(UTC) + timedelta(hours=2)
    await sql("UPDATE subscriptions SET period_end = :t", t=soon)
    await sql("UPDATE subscriptions SET payment_method_id = 'fake_card_0002' WHERE user_id = :u", u=failing)
    await sql("UPDATE payments SET created_at = now() - interval '1 day'")

    await subscriptions.tick()
    state = (await client.get("/subscription", headers=bearer(ok))).json()
    assert datetime.fromisoformat(state["period_end"]) == subscriptions.add_month(soon)  # продлено сохранённой картой
    assert (await client.get("/payments", headers=bearer(ok))).json()[0]["recurring"] is True
    assert [e["data"]["reason"] for e in await outbox("billing.subscription.changed")][-1] == "renewed"
    failed = [e["data"] for e in await outbox("billing.payment.failed")]
    assert failed[0]["user_id"] == str(failing) and failed[0]["recurring"] is True
    reminded = [e["data"]["user_id"] for e in await outbox("billing.subscription.expiring")]
    assert reminded == [str(manual)]  # без автопродления — напоминание, один раз
    await subscriptions.tick()
    assert len(await outbox("billing.subscription.expiring")) == 1

    # Период кончился — бесплатный тариф и событие; для неудачного автопродления пробуем ещё, после 3 отказов — выключаем.
    await sql("UPDATE subscriptions SET period_end = now() - interval '1 minute' WHERE user_id IN (:a, :b)", a=manual, b=failing)
    for _ in range(3):
        await sql("UPDATE payments SET created_at = now() - interval '7 hours'")
        await subscriptions.tick()
    assert (await client.get("/subscription", headers=bearer(manual))).json()["plan"] == "free"
    expired = [e["data"] for e in await outbox("billing.subscription.changed") if e["data"]["reason"] == "expired"]
    assert {e["user_id"] for e in expired} == {str(manual), str(failing)} and expired[0]["plan"] == "free"
    assert (await client.get("/subscription", headers=bearer(failing))).json()["auto_renew"] is False

    # Снова оплатили — тариф вернулся.
    await buy(client, manual)
    assert (await client.get("/subscription", headers=bearer(manual))).json()["plan"] == "basic"
