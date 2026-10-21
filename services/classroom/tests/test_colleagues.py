"""Мои коллеги (решение №56): заявка по логину или почте, коллега принимает."""

from uuid import uuid4

from testmatica_common.internal import INTERNAL_HEADER

from app.config import settings

from .conftest import bearer, outbox, student_bearer


async def test_colleague_request_accept_remove(client, teacher, fake_identity):
    petr = fake_identity.add("petr@example.com", "Петров Пётр", roles=("teacher",))
    fake_identity.add("olya", "Смирнова Оля")
    assert (await client.post("/colleagues", json={"identifier": "olya"}, headers=bearer(teacher))).json()["error"]["code"] == "not_a_teacher"
    assert (await client.post("/colleagues", json={"identifier": "nobody"}, headers=bearer(teacher))).status_code == 404
    assert (await client.post("/colleagues", json={"identifier": "x"}, headers=student_bearer(uuid4()))).status_code == 403

    sent = (await client.post("/colleagues", json={"identifier": "petr@example.com"}, headers=bearer(teacher))).json()
    assert [(o["full_name"], o["user_id"]) for o in sent["outgoing"]] == [("Петров Пётр", str(petr))] and sent["colleagues"] == []
    again = await client.post("/colleagues", json={"identifier": "petr@example.com"}, headers=bearer(teacher))
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_requested"
    requested = await outbox("classroom.colleague.requested")
    assert requested[0]["data"]["to_id"] == str(petr) and requested[0]["data"]["actor_name"] == "Мария Ивановна"

    # Пётр видит входящую заявку и принимает.
    mine = (await client.get("/colleagues", headers=bearer(petr))).json()
    assert [i["user_id"] for i in mine["incoming"]] == [str(teacher)]
    assert (await client.post(f"/colleagues/requests/{mine['incoming'][0]['id']}/accept", headers=bearer(uuid4()))).status_code == 404
    accepted = (await client.post(f"/colleagues/requests/{mine['incoming'][0]['id']}/accept", headers=bearer(petr))).json()
    assert [c["user_id"] for c in accepted["colleagues"]] == [str(teacher)] and accepted["incoming"] == []
    assert [c["full_name"] for c in (await client.get("/colleagues", headers=bearer(teacher))).json()["colleagues"]] == ["Петров Пётр"]
    assert (await outbox("classroom.colleague.accepted"))[0]["data"]["to_id"] == str(teacher)
    h = {INTERNAL_HEADER: settings.internal_token}
    check = await client.get("/internal/colleagues/check", params={"teacher_id": str(petr), "other_id": str(teacher)}, headers=h)
    assert check.json() == {"colleagues": True}

    # Убрать из коллег — связь пропадает у обоих.
    after = (await client.delete(f"/colleagues/{petr}", headers=bearer(teacher))).json()
    assert after["colleagues"] == []
    assert (await client.get("/colleagues", headers=bearer(petr))).json()["colleagues"] == []


async def test_counter_request_and_decline(client, teacher, fake_identity):
    """Встречная заявка — сразу коллеги; отклонённая заявка исчезает."""
    anna = fake_identity.add("anna", "Анна Сергеевна", roles=("teacher",))
    fake_identity.add("maria", "Мария Ивановна", roles=("teacher",), user_id=teacher)
    await client.post("/colleagues", json={"identifier": "anna"}, headers=bearer(teacher))
    both = (await client.post("/colleagues", json={"identifier": "maria"}, headers=bearer(anna))).json()
    assert [c["user_id"] for c in both["colleagues"]] == [str(teacher)]
    assert (await client.post("/colleagues", json={"identifier": "maria"}, headers=bearer(anna))).json()["error"]["code"] == "already_colleagues"

    ivan = fake_identity.add("ivan", "Иван Петрович", roles=("teacher",))
    await client.post("/colleagues", json={"identifier": "ivan"}, headers=bearer(teacher))
    req = (await client.get("/colleagues", headers=bearer(ivan))).json()["incoming"][0]
    declined = (await client.post(f"/colleagues/requests/{req['id']}/decline", headers=bearer(ivan))).json()
    assert declined["incoming"] == [] and declined["colleagues"] == []
    assert (await client.get("/colleagues", headers=bearer(teacher))).json()["outgoing"] == []


async def befriend(client, fake_identity, teacher, login="petr", name="Петров Пётр"):
    """Коллега педагога teacher — уже принял заявку."""
    other = fake_identity.add(login, name, roles=("teacher",))
    await client.post("/colleagues", json={"identifier": login}, headers=bearer(teacher))
    req = (await client.get("/colleagues", headers=bearer(other))).json()["incoming"][0]
    await client.post(f"/colleagues/requests/{req['id']}/accept", headers=bearer(other))
    return other


async def add_student(client, teacher, group_id, last_name):
    sid = (await client.post("/students/manual", json={"last_name": last_name, "first_name": "Ученик"},
                             headers=bearer(teacher))).json()["student"]["student_id"]
    await client.post(f"/groups/{group_id}/members", json={"student_id": sid}, headers=bearer(teacher))
    return sid


async def test_share_class_with_colleague(client, teacher, fake_identity):
    """Поделиться классом (решение №57): коллега видит класс и учеников, они — его ученики; управлять составом
    не может; новые ученики класса тоже становятся его; закрыть доступ — ученики «от коллеги» уходят."""
    from testmatica_common.internal import INTERNAL_HEADER

    from app.config import settings

    petr = await befriend(client, fake_identity, teacher)
    stranger = uuid4()
    group = (await client.post("/groups", json={"title": "7А", "kind": "class"}, headers=bearer(teacher))).json()
    anya = await add_student(client, teacher, group["id"], "Петрова")

    url = f"/groups/{group['id']}/shares"
    assert (await client.post(url, json={"colleague_id": str(stranger)}, headers=bearer(teacher))).status_code == 404
    shared = (await client.post(url, json={"colleague_id": str(petr)}, headers=bearer(teacher))).json()
    assert [s["full_name"] for s in shared["shares"]] == ["Петров Пётр"]
    assert (await outbox("classroom.group.shared"))[0]["data"]["colleague_id"] == str(petr)

    # У коллеги: класс с пометкой, ученики — его ученики (событие link.created «от коллеги»).
    mine = (await client.get("/groups", headers=bearer(petr))).json()
    assert [(g["title"], g["shared"], g["owner_name"]) for g in mine] == [("7А", True, "Мария Ивановна")]
    detail = (await client.get(f"/groups/{group['id']}", headers=bearer(petr))).json()
    assert [m["student_id"] for m in detail["members"]] == [anya] and detail["shares"] == []
    links = [e["data"] for e in await outbox("classroom.link.created") if e["data"]["teacher_id"] == str(petr)]
    assert [(link["student_id"], link["source"]) for link in links] == [(anya, "colleague")]
    h = {INTERNAL_HEADER: settings.internal_token}
    info = await client.get(f"/internal/groups/{group['id']}", params={"teacher_id": str(petr)}, headers=h)
    assert info.status_code == 200 and info.json()["member_ids"] == [anya]  # расписание и тесты пускают коллегу

    # Управлять составом и классом коллега не может; отвязать ученика класса — тоже.
    assert (await client.patch(f"/groups/{group['id']}", json={"title": "x"}, headers=bearer(petr))).status_code == 403
    assert (await client.delete(f"/groups/{group['id']}/members/{anya}", headers=bearer(petr))).status_code == 403
    unlink = await client.delete(f"/students/{anya}", headers=bearer(petr))
    assert unlink.status_code == 409 and unlink.json()["error"]["code"] == "colleague_student"

    # Новый ученик класса — сразу и ученик коллеги; ушёл из класса — уже нет.
    vasya = await add_student(client, teacher, group["id"], "Васильев")
    assert {s["student_id"] for s in (await client.get("/students", headers=bearer(petr))).json()} == {anya, vasya}
    await client.delete(f"/groups/{group['id']}/members/{vasya}", headers=bearer(teacher))
    assert {s["student_id"] for s in (await client.get("/students", headers=bearer(petr))).json()} == {anya}

    # Закрыть доступ: класса у коллеги нет, ученики «от коллеги» больше не его.
    assert (await client.delete(f"{url}/{petr}", headers=bearer(stranger))).status_code == 404
    assert (await client.delete(f"{url}/{petr}", headers=bearer(teacher))).status_code == 204
    assert (await client.get("/groups", headers=bearer(petr))).json() == []
    assert (await client.get("/students", headers=bearer(petr))).json() == []
    assert (await client.get(f"/groups/{group['id']}", headers=bearer(petr))).status_code == 404


async def test_removing_colleague_closes_shared_classes(client, teacher, fake_identity):
    petr = await befriend(client, fake_identity, teacher)
    group = (await client.post("/groups", json={"title": "8Б", "kind": "class"}, headers=bearer(teacher))).json()
    await add_student(client, teacher, group["id"], "Иванов")
    await client.post(f"/groups/{group['id']}/shares", json={"colleague_id": str(petr)}, headers=bearer(teacher))
    # Коллега сам отказывается от класса — можно; а убрать из коллег — закрывает всё.
    await client.delete(f"/colleagues/{teacher}", headers=bearer(petr))
    assert (await client.get("/groups", headers=bearer(petr))).json() == []
    assert (await client.get("/students", headers=bearer(petr))).json() == []
    assert (await client.get(f"/groups/{group['id']}", headers=bearer(teacher))).json()["shares"] == []


async def test_share_permissions(client, teacher, fake_identity):
    """Права коллеги в общем классе (решение №61): добавлять своих учеников (убирать — только их), управлять составом;
    ученик коллеги становится учеником владельца и уходит от него, когда его убрали из класса."""
    petr = await befriend(client, fake_identity, teacher)
    group = (await client.post("/groups", json={"title": "7А", "kind": "class"}, headers=bearer(teacher))).json()
    gid = group["id"]
    anya = await add_student(client, teacher, gid, "Петрова")
    url = f"/groups/{gid}/shares"
    shared = (await client.post(url, json={"colleague_id": str(petr), "permissions": ["add_students", "class_works"]},
                                headers=bearer(teacher))).json()
    assert shared["shares"][0]["permissions"] == ["add_students", "class_works"]

    # Свой ученик Петра — в класс; чужого (ученика класса «от коллеги») добавить нельзя.
    kolya = (await client.post("/students/manual", json={"last_name": "Колин", "first_name": "Коля"},
                               headers=bearer(petr))).json()["student"]["student_id"]
    assert (await client.post(f"/groups/{gid}/members", json={"student_id": kolya}, headers=bearer(petr))).status_code == 204
    detail = (await client.get(f"/groups/{gid}", headers=bearer(petr))).json()
    assert detail["permissions"] == ["add_students", "class_works"]
    assert {m["student_id"]: (m["added_by"], m["can_remove"]) for m in detail["members"]} == {
        anya: (None, False), kolya: (str(petr), True)}
    owner_students = {s["student_id"]: s["source"] for s in (await client.get("/students", headers=bearer(teacher))).json()}
    assert owner_students[kolya] == "colleague"  # ученик коллеги — теперь и ученик владельца
    h = {INTERNAL_HEADER: settings.internal_token}
    info = (await client.get(f"/internal/groups/{gid}", params={"teacher_id": str(petr)}, headers=h)).json()
    assert info["permissions"] == ["add_students", "class_works"]
    assert [(t["teacher_id"], "owner" in t["permissions"]) for t in info["teachers"]] == [(str(teacher), True), (str(petr), False)]
    works = (await client.get(f"/internal/teachers/{petr}/groups", params={"with_permission": "class_works"}, headers=h)).json()
    assert [g["id"] for g in works] == [gid]

    # Убрать: Пётр — только своего, владелец — любого; убрали Колю — у владельца он больше не ученик.
    assert (await client.delete(f"/groups/{gid}/members/{anya}", headers=bearer(petr))).status_code == 403
    assert (await client.patch(f"/groups/{gid}", json={"title": "8А"}, headers=bearer(petr))).status_code == 403
    assert (await client.delete(f"/groups/{gid}/members/{kolya}", headers=bearer(petr))).status_code == 204
    assert kolya not in {s["student_id"] for s in (await client.get("/students", headers=bearer(teacher))).json()}
    assert kolya in {s["student_id"] for s in (await client.get("/students", headers=bearer(petr))).json()}

    # «Управлять составом»: убирает любого и меняет класс, но платность — только владелец.
    await client.put(f"{url}/{petr}", json={"permissions": ["manage"]}, headers=bearer(teacher))
    assert (await client.patch(f"/groups/{gid}", json={"title": "8А"}, headers=bearer(petr))).json()["title"] == "8А"
    assert (await client.patch(f"/groups/{gid}", json={"paid": True}, headers=bearer(petr))).status_code == 403
    assert (await client.delete(f"/groups/{gid}/members/{anya}", headers=bearer(petr))).status_code == 204
    assert (await client.post(f"/groups/{gid}/archive", headers=bearer(petr))).status_code == 404
