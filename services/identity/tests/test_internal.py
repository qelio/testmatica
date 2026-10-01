from uuid import uuid4

from testmatica_common.internal import INTERNAL_HEADER

from app.config import settings

from .conftest import events, register

H = {INTERNAL_HEADER: settings.internal_token}


async def test_internal_requires_token(client):
    resp = await client.get("/internal/users/lookup", params={"identifier": "x"})
    assert resp.status_code == 403
    resp = await client.get("/internal/users/lookup", params={"identifier": "x"}, headers={INTERNAL_HEADER: "wrong"})
    assert resp.status_code == 403


async def test_managed_student_can_log_in_without_2fa(client):
    teacher_id = uuid4()
    resp = await client.post(
        "/internal/managed-students", json={"teacher_id": str(teacher_id), "last_name": "Сидоров", "first_name": " Петя "}, headers=H
    )
    assert resp.status_code == 201, resp.text
    creds = resp.json()
    assert creds["login"].startswith("petya")
    assert creds["user"]["full_name"] == "Сидоров Петя"  # фамилия первой, логин — по имени
    assert creds["user"]["managed_by_teacher_id"] == str(teacher_id)

    login = await client.post("/auth/login", json={"identifier": creds["login"], "password": creds["password"]})
    assert login.status_code == 200
    body = login.json()
    assert body["status"] == "authenticated"
    assert body["user"]["roles"] == ["student"]

    registered = await events("identity.user.registered")
    assert registered[-1]["actor_id"] == str(teacher_id)


async def test_managed_student_with_chosen_login(client):
    teacher = str(uuid4())
    body = {"teacher_id": teacher, "last_name": "Козлова", "first_name": "Аня", "login": "Anya.K", "password": "simple1"}
    first = await client.post("/internal/managed-students", json=body, headers=H)
    assert first.status_code == 201
    assert first.json()["login"] == "anya.k"
    assert first.json()["password"] == "simple1"

    dup = await client.post("/internal/managed-students", json=body, headers=H)
    assert dup.status_code == 409

    bad = await client.post("/internal/managed-students", json={**body, "login": "кириллица"}, headers=H)
    assert bad.status_code == 422


async def test_only_owner_teacher_can_update(client):
    teacher = str(uuid4())
    creds = (
        await client.post("/internal/managed-students", json={"teacher_id": teacher, "last_name": "Смирнова", "first_name": "Оля"}, headers=H)
    ).json()
    uid = creds["user"]["id"]

    other = await client.patch(
        f"/internal/managed-students/{uid}", json={"teacher_id": str(uuid4()), "name": {"last_name": "X", "first_name": "Y"}}, headers=H
    )
    assert other.status_code == 404

    reset = await client.patch(
        f"/internal/managed-students/{uid}",
        json={"teacher_id": teacher, "name": {"last_name": "Смирнова", "first_name": "Ольга"}, "reset_password": True},
        headers=H,
    )
    assert reset.status_code == 200
    new_password = reset.json()["password"]
    assert new_password and new_password != creds["password"]
    assert reset.json()["user"]["full_name"] == "Смирнова Ольга"

    old = await client.post("/auth/login", json={"identifier": creds["login"], "password": creds["password"]})
    assert old.status_code == 401
    ok = await client.post("/auth/login", json={"identifier": creds["login"], "password": new_password})
    assert ok.status_code == 200


async def test_lookup(client):
    await register(client, "found@example.com")
    resp = await client.get("/internal/users/lookup", params={"identifier": "FOUND@example.com"}, headers=H)
    assert resp.status_code == 200
    assert resp.json()["roles"] == ["student"]

    missing = await client.get("/internal/users/lookup", params={"identifier": "nobody"}, headers=H)
    assert missing.status_code == 404
