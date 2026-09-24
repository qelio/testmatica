from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from testmatica_common.auth import TokenVerifier

from app.config import settings
from app.deps import db, signing_key
from app.models import RefreshToken

from .conftest import PASSWORD, events, login, register, sent_code


async def test_full_flow_register_verify_login_refresh_logout(client):
    reg = await register(client, "Ivan@Example.com")
    assert reg["destination"] == "iv***@example.com"

    session = await login(client, "ivan@example.com")
    assert session["status"] == "authenticated"
    assert session["user"]["roles"] == ["student"]
    assert session["user"]["email"] == "ivan@example.com"
    assert client.cookies.get(settings.refresh_cookie_name)

    token = session["access_token"]
    me = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["two_factor_method"] == "email"

    refreshed = await client.post("/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["access_token"] != token

    assert (await client.post("/auth/logout")).status_code == 204
    assert (await client.post("/auth/refresh")).json()["error"]["code"] == "no_session"


async def test_access_token_is_verifiable_by_other_services(client):
    await register(client, "t@example.com", role="teacher")
    session = await login(client, "t@example.com")

    jwks = (await client.get("/.well-known/jwks.json")).json()
    assert jwks == signing_key.jwks
    verifier = TokenVerifier(settings.jwt_issuer, settings.jwt_audience, static_jwks=jwks)
    claims = await verifier.verify(session["access_token"])
    assert claims["roles"] == ["teacher"]
    assert claims["teacher_mode"] == "school"
    assert claims["typ"] == "access"


async def test_register_validation(client):
    base = {"email": "a@example.com", "password": PASSWORD, "full_name": "А", "role": "student", "consent_pdn": True}

    no_consent = await client.post("/auth/register", json={**base, "consent_pdn": False})
    assert no_consent.status_code == 422

    weak = await client.post("/auth/register", json={**base, "password": "onlyletters"})
    assert weak.status_code == 422
    assert weak.json()["error"]["details"]["fields"][0]["field"] == "password"

    admin = await client.post("/auth/register", json={**base, "role": "admin"})
    assert admin.status_code == 422

    assert (await client.post("/auth/register", json=base)).status_code == 201
    dup = await client.post("/auth/register", json={**base, "email": "A@EXAMPLE.COM"})
    assert dup.status_code == 409


async def test_registration_publishes_event(client):
    reg = await register(client, "e@example.com")
    registered = await events("identity.user.registered")
    assert len(registered) == 1
    assert registered[0]["data"] == {
        "user_id": reg["user_id"],
        "full_name": "Иван Петров",
        "login": None,
        "roles": ["student"],
        "status": "pending_verification",
    }
    assert len(await events("identity.user.email_verified")) == 1


async def test_login_before_verification_sends_new_code(client):
    await register(client, "p@example.com", verify=False)
    resp = await client.post("/auth/login", json={"identifier": "p@example.com", "password": PASSWORD})
    assert resp.status_code == 403
    error = resp.json()["error"]
    assert error["code"] == "email_not_verified"

    code = await sent_code("p@example.com", "email_verification")
    ok = await client.post("/auth/verify-email", json={"challenge_id": error["details"]["challenge_id"], "code": code})
    assert ok.status_code == 200
    # Подтверждение email сразу открывает сессию.
    assert ok.json()["status"] == "authenticated"
    assert (await client.post("/auth/refresh")).status_code == 200


async def test_wrong_code_attempts_are_limited(client):
    reg = await register(client, "w@example.com", verify=False)
    real = await sent_code("w@example.com", "email_verification")
    wrong = "000000" if real != "000000" else "111111"

    for left in range(settings.otp_max_attempts - 1, -1, -1):
        resp = await client.post("/auth/verify-email", json={"challenge_id": reg["challenge_id"], "code": wrong})
        assert resp.json()["error"]["details"]["attempts_left"] == left

    blocked = await client.post("/auth/verify-email", json={"challenge_id": reg["challenge_id"], "code": real})
    assert blocked.json()["error"]["code"] == "too_many_attempts"


async def test_resend_is_rate_limited(client):
    reg = await register(client, "r@example.com", verify=False)
    resp = await client.post("/auth/resend-code", json={"challenge_id": reg["challenge_id"]})
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "resend_too_early"


async def test_brute_force_locks_account(client):
    await register(client, "b@example.com")
    for _ in range(settings.login_max_failures):
        resp = await client.post("/auth/login", json={"identifier": "b@example.com", "password": "wrong-pass-1"})
        assert resp.status_code == 401
    locked = await client.post("/auth/login", json={"identifier": "b@example.com", "password": PASSWORD})
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "account_locked"


async def test_unknown_user_gets_same_error(client):
    resp = await client.post("/auth/login", json={"identifier": "nobody@example.com", "password": PASSWORD})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


async def test_refresh_token_reuse_revokes_family(client):
    await register(client, "s@example.com")
    await login(client, "s@example.com")
    stolen = client.cookies.get(settings.refresh_cookie_name)

    assert (await client.post("/auth/refresh")).status_code == 200
    # Выходим за «окно параллельных запросов»: старый токен отозван давно.
    async with db.sessionmaker() as s, s.begin():
        await s.execute(
            update(RefreshToken)
            .where(RefreshToken.revoked_at.is_not(None))
            .values(revoked_at=datetime.now(UTC) - timedelta(minutes=1))
        )

    current = client.cookies.get(settings.refresh_cookie_name)
    client.cookies.set(settings.refresh_cookie_name, stolen, path="/auth")
    reuse = await client.post("/auth/refresh")
    assert reuse.json()["error"]["code"] == "session_revoked"

    # Легитимный токен из той же цепочки тоже больше не работает.
    client.cookies.set(settings.refresh_cookie_name, current, path="/auth")
    assert (await client.post("/auth/refresh")).status_code == 401


async def test_password_reset(client):
    await register(client, "f@example.com")
    await login(client, "f@example.com")

    forgot = await client.post("/auth/password/forgot", json={"email": "f@example.com"})
    assert forgot.status_code == 202
    code = await sent_code("f@example.com", "password_reset")
    reset = await client.post(
        "/auth/password/reset",
        json={"challenge_id": forgot.json()["challenge_id"], "code": code, "new_password": "brand-new-2"},
    )
    assert reset.status_code == 200

    # Все сессии завершены, старый пароль не подходит.
    assert (await client.post("/auth/refresh")).status_code == 401
    old = await client.post("/auth/login", json={"identifier": "f@example.com", "password": PASSWORD})
    assert old.status_code == 401
    await login(client, "f@example.com", password="brand-new-2")


async def test_forgot_password_for_unknown_email_looks_the_same(client):
    resp = await client.post("/auth/password/forgot", json={"email": "ghost@example.com"})
    assert resp.status_code == 202
    assert "challenge_id" in resp.json()


async def test_teacher_mode_switch(client):
    await register(client, "teacher@example.com", role="teacher")
    token = (await login(client, "teacher@example.com"))["access_token"]
    resp = await client.put("/me/teacher-mode", json={"mode": "tutor"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["user"]["teacher_mode"] == "tutor"
    assert len(await events("identity.user.teacher_mode_changed")) == 1

    await register(client, "student@example.com")
    student = (await login(client, "student@example.com"))["access_token"]
    forbidden = await client.put(
        "/me/teacher-mode", json={"mode": "tutor"}, headers={"Authorization": f"Bearer {student}"}
    )
    assert forbidden.status_code == 403


async def test_me_requires_valid_token(client):
    assert (await client.get("/me")).status_code == 401
    bad = await client.get("/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401
