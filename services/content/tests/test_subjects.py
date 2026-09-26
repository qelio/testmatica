from uuid import uuid4

from .conftest import bearer, outbox


async def test_subjects_directory_managed_by_moderators(client):
    mod = bearer(uuid4(), ("moderator",))
    before = (await client.get("/subjects")).json()  # открыт без входа
    assert any(s["name"] == "Математика" for s in before)
    assert (await client.post("/subjects", json={"name": "Астрономия"}, headers=bearer(uuid4()))).status_code == 403

    # Справочник между запусками тестов не очищается — имя уникальное.
    name = f"Астрономия {uuid4().hex[:6]}"
    astro = (await client.post("/subjects", json={"name": f"  {name} "}, headers=mod)).json()
    assert astro["name"] == name
    dup = await client.post("/subjects", json={"name": name.lower()}, headers=mod)
    assert dup.json()["error"]["code"] == "subject_exists"

    renamed = (await client.patch(f"/subjects/{astro['id']}", json={"name": f"{name} и космос"}, headers=mod)).json()
    assert renamed["name"] == f"{name} и космос"
    event = (await outbox("content.subject.updated"))[-1]["data"]
    assert (event["old_name"], event["name"]) == (name, f"{name} и космос")

    # Скрытый предмет пропадает из выбора, но остаётся у модератора.
    await client.patch(f"/subjects/{astro['id']}", json={"hidden": True}, headers=mod)
    assert all(s["id"] != astro["id"] for s in (await client.get("/subjects")).json())
    assert any(s["id"] == astro["id"] and s["hidden"] for s in (await client.get("/subjects", params={"all": True})).json())
