from uuid import uuid4

from testmatica_common.testing import make_envelope

from app import people
from app.deps import db
from app.models import Person

from .conftest import bearer, outbox, student_bearer


async def create_group(client, teacher, title="7А", kind="class", mode="school"):
    resp = await client.post("/groups", json={"title": title, "kind": kind}, headers=bearer(teacher, mode=mode))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_groups_crud_and_isolation(client, teacher):
    group = await create_group(client, teacher, title="  7А  ")
    assert group["title"] == "7А"
    assert group["mode"] == "school"

    # Группы разделены по режимам педагога.
    await create_group(client, teacher, title="ЕГЭ", kind="group", mode="tutor")
    school = (await client.get("/groups", headers=bearer(teacher))).json()
    assert [g["title"] for g in school] == ["7А"]
    tutor = (await client.get("/groups", headers=bearer(teacher, mode="tutor"))).json()
    assert [g["title"] for g in tutor] == ["ЕГЭ"]

    upd = await client.patch(f"/groups/{group['id']}", json={"subject": "Алгебра"}, headers=bearer(teacher))
    assert upd.json()["subject"] == "Алгебра" and upd.json()["title"] == "7А"

    # Чужой педагог группу не видит.
    other = uuid4()
    assert (await client.get(f"/groups/{group['id']}", headers=bearer(other))).status_code == 404

    arch = await client.post(f"/groups/{group['id']}/archive", headers=bearer(teacher))
    assert arch.json()["archived"] is True
    assert (await client.get("/groups", headers=bearer(teacher))).json() == []
    assert len((await client.get("/groups?archived=true", headers=bearer(teacher))).json()) == 1


async def test_students_cannot_use_teacher_endpoints(client):
    assert (await client.get("/groups", headers=student_bearer(uuid4()))).status_code == 403
    assert (await client.get("/students", headers=student_bearer(uuid4()))).status_code == 403


async def test_manual_student(client, teacher, fake_identity):
    group = await create_group(client, teacher)
    resp = await client.post(
        "/students/manual",
        json={"full_name": "Петя Сидоров", "login": "petya", "group_id": group["id"]},
        headers=bearer(teacher),
    )
    assert resp.status_code == 201, resp.text
    creds = resp.json()
    assert creds["login"] == "petya" and creds["password"]
    student = creds["student"]
    assert student["managed"] is True
    assert student["status"] == "active"
    assert student["group_ids"] == [group["id"]]

    detail = (await client.get(f"/groups/{group['id']}", headers=bearer(teacher))).json()
    assert [m["full_name"] for m in detail["members"]] == ["Петя Сидоров"]
    assert detail["student_count"] == 1

    sid = student["student_id"]
    renamed = await client.patch(f"/students/{sid}", json={"full_name": "Пётр Сидоров"}, headers=bearer(teacher))
    assert renamed.json()["full_name"] == "Пётр Сидоров"
    reset = await client.post(f"/students/{sid}/reset-password", headers=bearer(teacher))
    assert reset.json()["password"] == "new-pass-2"

    created = await outbox("classroom.link.created")
    assert created[0]["data"]["source"] == "manual"


async def test_link_request_accept_flow(client, teacher, fake_identity):
    sid = fake_identity.add("vasya@example.com", "Вася Пупкин")
    group = await create_group(client, teacher)

    resp = await client.post(
        "/students/requests", json={"identifier": "Vasya@example.com", "group_id": group["id"]}, headers=bearer(teacher)
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "pending"
    assert resp.json()["managed"] is False

    requested = await outbox("classroom.link.requested")
    assert requested[0]["data"]["teacher_name"] == "Мария Ивановна"

    mine = (await client.get("/me/teachers", headers=student_bearer(sid))).json()
    assert mine[0]["status"] == "pending" and mine[0]["full_name"] == "Мария Ивановна"

    # Нельзя менять аккаунт ученика, который зарегистрировался сам.
    assert (await client.patch(f"/students/{sid}", json={"full_name": "X"}, headers=bearer(teacher))).status_code == 404

    ok = await client.post(f"/me/requests/{mine[0]['link_id']}/accept", headers=student_bearer(sid))
    assert ok.status_code == 204
    groups = (await client.get("/me/groups", headers=student_bearer(sid))).json()
    assert [(g["title"], g["teacher_name"]) for g in groups] == [("7А", "Мария Ивановна")]

    again = await client.post(f"/me/requests/{mine[0]['link_id']}/accept", headers=student_bearer(sid))
    assert again.status_code == 404

    dup = await client.post("/students/requests", json={"identifier": "vasya@example.com"}, headers=bearer(teacher))
    assert dup.status_code == 409


async def test_link_request_decline(client, teacher, fake_identity):
    sid = fake_identity.add("kolya", "Коля")
    await client.post("/students/requests", json={"identifier": "kolya"}, headers=bearer(teacher))
    link_id = (await client.get("/me/teachers", headers=student_bearer(sid))).json()[0]["link_id"]

    # Чужой ученик не может ответить на запрос.
    assert (await client.post(f"/me/requests/{link_id}/decline", headers=student_bearer(uuid4()))).status_code == 404
    assert (await client.post(f"/me/requests/{link_id}/decline", headers=student_bearer(sid))).status_code == 204
    assert (await client.get("/students", headers=bearer(teacher))).json() == []
    assert (await outbox("classroom.link.declined"))[0]["data"]["student_name"] == "Коля"


async def test_link_request_errors(client, teacher, fake_identity):
    fake_identity.add("teacher2", "Другой педагог", roles=("teacher",))
    fake_identity.add("me", "Сам", roles=("teacher", "student"), user_id=teacher)

    missing = await client.post("/students/requests", json={"identifier": "ghost"}, headers=bearer(teacher))
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "user_not_found"
    not_student = await client.post("/students/requests", json={"identifier": "teacher2"}, headers=bearer(teacher))
    assert not_student.json()["error"]["code"] == "not_a_student"
    self_link = await client.post("/students/requests", json={"identifier": "me"}, headers=bearer(teacher))
    assert self_link.json()["error"]["code"] == "self_link"


async def test_members_require_active_link_and_unlink_removes_from_groups(client, teacher, fake_identity):
    group = await create_group(client, teacher)
    stranger = uuid4()
    resp = await client.post(f"/groups/{group['id']}/members", json={"student_id": str(stranger)}, headers=bearer(teacher))
    assert resp.status_code == 404

    sid = (
        await client.post("/students/manual", json={"full_name": "Аня"}, headers=bearer(teacher))
    ).json()["student"]["student_id"]
    assert (
        await client.post(f"/groups/{group['id']}/members", json={"student_id": sid}, headers=bearer(teacher))
    ).status_code == 204
    assert (await client.get(f"/groups/{group['id']}", headers=bearer(teacher))).json()["student_count"] == 1

    assert (await client.delete(f"/groups/{group['id']}/members/{sid}", headers=bearer(teacher))).status_code == 204
    assert (await client.get(f"/groups/{group['id']}", headers=bearer(teacher))).json()["student_count"] == 0

    await client.post(f"/groups/{group['id']}/members", json={"student_id": sid}, headers=bearer(teacher))
    assert (await client.delete(f"/students/{sid}", headers=bearer(teacher))).status_code == 204
    assert (await client.get(f"/groups/{group['id']}", headers=bearer(teacher))).json()["members"] == []
    assert (await client.get("/students", headers=bearer(teacher))).json() == []


async def test_invitation_flow(client, teacher):
    group = await create_group(client, teacher)
    inv = await client.post(
        "/invitations", json={"email": "New@Example.com", "group_id": group["id"]}, headers=bearer(teacher)
    )
    assert inv.status_code == 201
    assert inv.json()["email"] == "new@example.com"

    command = (await outbox("notification.email"))[0]["data"]
    assert command["template"] == "invitation"
    assert command["params"]["group_text"] == " в классе «7А»"
    token = command["params"]["url"].rsplit("/", 1)[1]

    public = (await client.get(f"/invitations/token/{token}")).json()
    assert public == {"status": "valid", "teacher_name": "Мария Ивановна", "group_title": "7А", "group_kind": "class"}

    # Принять может только ученик.
    assert (await client.post(f"/invitations/token/{token}/accept", headers=bearer(uuid4()))).status_code == 403

    sid = uuid4()
    assert (await client.post(f"/invitations/token/{token}/accept", headers=student_bearer(sid))).status_code == 204
    assert (await client.get("/me/groups", headers=student_bearer(sid))).json()[0]["title"] == "7А"
    students = (await client.get("/students", headers=bearer(teacher))).json()
    assert students[0]["source"] == "invite"

    used = await client.post(f"/invitations/token/{token}/accept", headers=student_bearer(uuid4()))
    assert used.status_code == 410 and used.json()["error"]["code"] == "invitation_used"
    assert (await client.get("/invitations", headers=bearer(teacher))).json() == []


async def test_revoked_invitation(client, teacher):
    inv = (await client.post("/invitations", json={"email": "a@example.com"}, headers=bearer(teacher))).json()
    token = (await outbox("notification.email"))[0]["data"]["params"]["url"].rsplit("/", 1)[1]
    assert (await client.delete(f"/invitations/{inv['id']}", headers=bearer(uuid4()))).status_code == 404
    assert (await client.delete(f"/invitations/{inv['id']}", headers=bearer(teacher))).status_code == 204
    resp = await client.post(f"/invitations/token/{token}/accept", headers=student_bearer(uuid4()))
    assert resp.json()["error"]["code"] == "invitation_revoked"


async def test_people_replica_from_identity_events():
    uid = uuid4()
    async with db.sessionmaker() as s, s.begin():
        await people.on_identity_event(
            make_envelope("identity.user.registered", {"user_id": str(uid), "full_name": "Имя", "login": None, "roles": ["student"]}), s
        )
        await people.on_identity_event(
            make_envelope("identity.user.updated", {"user_id": str(uid), "full_name": "Новое имя", "login": "x"}), s
        )
    async with db.sessionmaker() as s:
        person = await s.get(Person, uid)
    assert (person.full_name, person.login, person.roles) == ("Новое имя", "x", ["student"])
