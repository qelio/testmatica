from uuid import uuid4

from .conftest import bearer, outbox

ADMIN = ("admin",)


async def test_landing_defaults_and_admin_edit(client, fakes):
    boss = uuid4()
    public = (await client.get("/site/landing")).json()
    assert public["hero"]["title"].startswith("Учите") and public["sections"]["teachers"] is True and public["latest_news"] == []
    assert (await client.get("/admin/site/landing", headers=bearer(uuid4(), ("moderator",)))).status_code == 403

    image = fakes.file(boss, "hero.png", "image/png")
    data = (await client.get("/admin/site/landing", headers=bearer(boss, ADMIN))).json()
    data["hero"] |= {"title": "ТестМатика — школа онлайн", "image_file_id": image}
    teacher = str(uuid4())
    data["teachers"]["items"] = [{"user_id": teacher, "note": "Лучший по ЕГЭ"}]
    data["sections"]["faq"] = False
    data["features"] = data["features"][:2]
    saved = await client.put("/admin/site/landing", json=data, headers=bearer(boss, ADMIN))
    assert saved.status_code == 200, saved.text
    assert saved.json()["hero_image_url"] == f"http://s3/{image}"
    public = (await client.get("/site/landing")).json()
    assert public["hero"]["title"] == "ТестМатика — школа онлайн" and public["teachers"]["items"][0]["note"] == "Лучший по ЕГЭ"
    assert public["sections"]["faq"] is False and len(public["features"]) == 2
    assert (await outbox("content.site.updated"))[0]["data"]["section"] == "landing"

    bad = data | {"hero": data["hero"] | {"primary_href": "javascript:alert(1)"}}
    assert (await client.put("/admin/site/landing", json=bad, headers=bearer(boss, ADMIN))).status_code == 422


async def test_news_draft_publish_and_list(client, fakes):
    boss = uuid4()
    cover = fakes.file(boss, "cover.jpg", "image/jpeg")
    body = {"title": "Запустили прокторинг!", "summary": "Коротко", "body": "## Подробно", "cover_file_id": cover}
    draft = (await client.post("/admin/site/news", json=body, headers=bearer(boss, ADMIN))).json()
    assert draft["status"] == "draft" and draft["slug"] == "zapustili-proktoring" and draft["cover_url"] == f"http://s3/{cover}"
    # Черновик не виден публично, администратору — виден (предпросмотр).
    assert (await client.get(f"/site/news/{draft['slug']}")).status_code == 404
    assert (await client.get(f"/site/news/{draft['slug']}", headers=bearer(boss, ADMIN))).status_code == 200
    assert (await client.get("/site/news")).json()["total"] == 0

    pub = (await client.put(f"/admin/site/news/{draft['id']}", json=body | {"status": "published"}, headers=bearer(boss, ADMIN))).json()
    assert pub["status"] == "published" and pub["published_at"]
    listed = (await client.get("/site/news")).json()
    assert listed["total"] == 1 and listed["items"][0]["title"] == "Запустили прокторинг!"
    assert (await client.get("/site/landing")).json()["latest_news"][0]["slug"] == "zapustili-proktoring"
    # Тот же заголовок — адрес уникализируется; занятый адрес руками — ошибка.
    twin = (await client.post("/admin/site/news", json={"title": "Запустили прокторинг!"}, headers=bearer(boss, ADMIN))).json()
    assert twin["slug"].startswith("zapustili-proktoring-") and twin["slug"] != pub["slug"]
    taken = await client.put(f"/admin/site/news/{twin['id']}", json={"title": "x", "slug": pub["slug"]}, headers=bearer(boss, ADMIN))
    assert taken.json()["error"]["code"] == "slug_taken"
    assert (await client.delete(f"/admin/site/news/{twin['id']}", headers=bearer(boss, ADMIN))).status_code == 204
    assert len((await client.get("/admin/site/news", headers=bearer(boss, ADMIN))).json()) == 1
