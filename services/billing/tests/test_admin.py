from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .conftest import INTERNAL, bearer, outbox
from .test_subscription import buy

ADMIN = ("admin",)


async def test_settings_change_price_and_limits(client):
    boss = bearer(uuid4(), ADMIN)
    assert (await client.get("/admin/settings", headers=bearer(uuid4()))).status_code == 403
    before = (await client.get("/admin/settings", headers=boss)).json()
    assert before["basic_price_rub"] == 490 and before["free_max_groups"] == 3

    bad = await client.put("/admin/settings", json={"values": {"free_max_groups": 0}}, headers=boss)
    assert bad.json()["error"]["code"] == "setting_out_of_range"
    assert (await client.put("/admin/settings", json={"values": {"magic": 1}}, headers=boss)).status_code == 422
    after = (await client.put("/admin/settings", json={"values": {"basic_price_rub": 590, "free_max_groups": 5}}, headers=boss)).json()
    assert after["basic_price_rub"] == 590 and after["free_max_groups"] == 5
    assert (await outbox("billing.settings.updated"))[0]["data"]["changes"]["basic_price_rub"] == {"from": 490, "to": 590}
    # Новая цена — сразу в тарифе и платежах; лимиты — сервисам через /internal/settings.
    teacher = uuid4()
    assert (await client.get("/subscription", headers=bearer(teacher))).json()["price_rub"] == 590
    pay = (await client.post("/subscription/checkout", json={"accept_offer": True}, headers=bearer(teacher))).json()
    assert pay["amount_rub"] == 590
    assert (await client.get("/internal/settings", headers=INTERNAL)).json()["free_max_groups"] == 5


async def test_payments_stats_and_grant(client):
    boss = bearer(uuid4(), ADMIN)
    a, b = uuid4(), uuid4()
    await buy(client, a)
    await buy(client, b, card="0002")  # отказ банка
    listed = (await client.get("/admin/payments", headers=boss)).json()
    assert {p["status"] for p in listed} == {"succeeded", "canceled"} and all(p["user_id"] for p in listed)
    assert len((await client.get("/admin/payments", params={"status": "succeeded"}, headers=boss)).json()) == 1

    s = (await client.get("/admin/stats", headers=boss)).json()
    assert s["subscribers"] == 1 and s["ever_paid"] == 1 and s["revenue_rub"] == 490 and s["months"][-1]["payments"] == 1

    # Ручное подключение без оплаты — с причиной, в аудит и уведомление.
    g = (await client.post(f"/admin/subscriptions/{b}/grant", json={"days": 14, "reason": "Сбой оплаты"}, headers=boss)).json()
    assert timedelta(days=13) < datetime.fromisoformat(g["period_end"]) - datetime.now(UTC) <= timedelta(days=14)
    assert (await client.get("/subscription", headers=bearer(b))).json()["plan"] == "basic"
    reasons = [e["data"]["reason"] for e in await outbox("billing.subscription.changed")]
    assert reasons[-1] == "granted"
    assert (await client.get("/admin/stats", headers=boss)).json()["subscribers"] == 2
