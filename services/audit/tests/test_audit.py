from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from testmatica_common.testing import make_envelope

from app.deps import db

from .conftest import bearer


async def test_events_are_recorded_once(audit_consumer):
    actor = uuid4()
    event = make_envelope("identity.user.logged_in", {"ip": "1.2.3.4"}, producer="identity", actor_id=actor)
    assert await audit_consumer.process(event) is True
    assert await audit_consumer.process(event) is False

    async with db.engine.connect() as conn:
        count = await conn.scalar(
            text("SELECT count(*) FROM audit_log WHERE event_id = :id"), {"id": event.event_id}
        )
    assert count == 1


@pytest.mark.parametrize(
    "statement",
    ["UPDATE audit_log SET type = 'x'", "DELETE FROM audit_log", "TRUNCATE audit_log"],
)
async def test_audit_log_is_append_only(audit_consumer, statement):
    await audit_consumer.process(make_envelope("test.event", {}))
    with pytest.raises(DBAPIError, match="append-only"):
        async with db.engine.begin() as conn:
            await conn.execute(text(statement))


async def test_api_is_admin_only(client, audit_consumer):
    actor = uuid4()
    await audit_consumer.process(make_envelope("identity.user.password_reset", {}, actor_id=actor))
    await audit_consumer.process(make_envelope("billing.lesson.paid", {}, actor_id=actor))

    student = await client.get("/audit", headers=bearer(uuid4(), ["student"]))
    assert student.status_code == 403

    admin = await client.get(
        "/audit", params={"actor_id": str(actor), "type_prefix": "identity."}, headers=bearer(uuid4(), ["admin"])
    )
    assert admin.status_code == 200
    assert [r["type"] for r in admin.json()] == ["identity.user.password_reset"]


async def test_user_history_and_stats(client, audit_consumer):
    admin_h = bearer(uuid4(), ["admin"])
    user, teacher = uuid4(), uuid4()
    before = (await client.get("/audit/stats", params={"days": 1}, headers=admin_h)).json()
    lessons_before = next(a["total"] for a in before["activity"] if a["type"] == "schedule.lesson.created")

    # Журнал только дописывается, поэтому считаем разницу «до/после».
    await audit_consumer.process(make_envelope("identity.user.banned", {"user_id": str(user)}, actor_id=uuid4()))
    await audit_consumer.process(make_envelope("identity.user.logged_in", {"user_id": str(user)}, actor_id=user))
    await audit_consumer.process(make_envelope("schedule.lesson.created", {"count": 10}, actor_id=teacher))
    await audit_consumer.process(make_envelope("academic.grade.created", {}, actor_id=teacher))

    history = (await client.get("/audit", params={"user_id": str(user)}, headers=admin_h)).json()
    assert {r["type"] for r in history} == {"identity.user.banned", "identity.user.logged_in"}  # сам и о нём

    after = (await client.get("/audit/stats", params={"days": 1}, headers=admin_h)).json()
    lessons = next(a for a in after["activity"] if a["type"] == "schedule.lesson.created")
    assert lessons["total"] - lessons_before == 10 and lessons["title"] == "Занятий запланировано"
    actions = [t["actions"] for t in after["top_teachers"]]
    assert actions == sorted(actions, reverse=True)
    assert (await client.get("/audit/stats", headers=bearer(uuid4(), ["moderator"]))).status_code == 403
