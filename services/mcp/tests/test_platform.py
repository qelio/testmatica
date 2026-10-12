"""Сервис mcp: ключ из заголовка, обмен на токен, ошибки сервисов, перенос картинок (решение №41)."""

import base64
import json

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from app import platform


def test_api_key_from_headers():
    assert platform.api_key({"authorization": "Bearer tm_abc123"}) == "tm_abc123"
    assert platform.api_key({"x-api-key": "tm_abc123"}) == "tm_abc123"
    for headers in (None, {}, {"authorization": "Bearer something"}):
        with pytest.raises(ToolError, match="Нет ключа доступа"):
            platform.api_key(headers)


@pytest.fixture
def platform_fake(monkeypatch):
    """identity (обмен ключа) и сервисы платформы — подменённые."""
    calls: list[tuple[str, str, dict | None]] = []

    def identity(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["key"] != "tm_good":
            return httpx.Response(401, json={"error": {"code": "invalid_api_key", "message": "Нет"}})
        return httpx.Response(200, json={"access_token": "user-token", "expires_in": 900, "user_id": "u", "full_name": "Иванова Мария"})

    def services(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer user-token"
        if request.url.path == "/files":  # загрузка картинки — multipart
            content = request.read()
            calls.append((request.method, request.url.path, {"multipart": content}))
            return httpx.Response(201, json={"id": "f2"})
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        if request.url.path == "/files/import":
            if "broken" in body["url"]:
                return httpx.Response(422, json={"error": {"code": "image_unavailable", "message": "Не удалось"}})
            return httpx.Response(201, json={"id": "f1"})
        if request.url.path == "/tasks" and request.method == "POST":
            return httpx.Response(422, json={"error": {"code": "validation_error", "message": "Некорректные данные", "details": {
                "fields": [{"field": "", "message": "Value error, Укажите правильный ответ"}, {"field": "title", "message": "обязательно"}]}}})
        return httpx.Response(200, json={"ok": True})

    platform._tokens.clear()
    monkeypatch.setattr(platform.identity, "transport", httpx.MockTransport(identity))
    monkeypatch.setattr(platform, "transport", httpx.MockTransport(services))
    return calls


async def test_call_as_user_and_errors(platform_fake):
    assert await platform.call("tm_good", "assessment", "GET", "/tasks") == {"ok": True}
    with pytest.raises(ToolError, match="недействителен"):
        await platform.call("tm_bad", "assessment", "GET", "/tasks")
    # Ошибки проверки — понятным текстом, чтобы Claude исправил и повторил.
    with pytest.raises(ToolError) as e:
        await platform.call("tm_good", "assessment", "POST", "/tasks", json={})
    assert str(e.value) == "Некорректные данные: Укажите правильный ответ; title: обязательно"


async def test_localize_images(platform_fake):
    text = 'Рисунок: ![граф](https://example.com/g.png "width=300") и ![x](https://example.com/broken.png) и ![s](/api/media/files/1/content)'
    out = await platform.localize_images("tm_good", text)
    assert out == ('Рисунок: ![граф](/api/media/files/f1/content "width=300") и ![x](https://example.com/broken.png) '
                   'и ![s](/api/media/files/1/content)')
    assert [c[1] for c in platform_fake] == ["/files/import", "/files/import"]


async def test_tests_tools(monkeypatch):
    """Тесты для Claude (решения №43, 44): задачи по номерам, привязка к модулю, «для всех», правка частями."""
    from types import SimpleNamespace

    from app import tools

    stored: dict = {}
    sent: list[tuple[str, str, dict | None]] = []

    def services(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        sent.append((request.method, request.url.path, body))
        path = request.url.path
        if path == "/tasks":
            n = int(request.url.params["q"])
            return httpx.Response(200, json={"items": [{"id": f"t{n}", "number": n}], "total": 1})
        if path.startswith("/tasks/"):
            tid = path.rsplit("/", 1)[1]
            return httpx.Response(200, json={"id": tid, "number": int(tid[1:]), "title": f"Задача {tid}"})
        if path == "/tests" and request.method == "POST" or path.startswith("/tests/") and request.method == "PUT":
            stored.update(body, id="q1")
            stored["module"] = {"id": body["module_id"], "title": "Миссия 1", "course_id": "c1", "course_title": "Вебоград"} \
                if body["module_id"] else None
            stored["items"] = [{"task": {"number": int(i["task_id"][1:]), "title": "З"}, "points": i["points"],
                                "solution_file": i["solution_file"]} for i in body["items"]]
            return httpx.Response(200, json=stored)
        if path.startswith("/tests/"):
            return httpx.Response(200, json=stored)
        return httpx.Response(404, json={"error": {"code": "not_found", "message": "Нет"}})

    platform._tokens.clear()
    monkeypatch.setattr(platform.identity, "transport", httpx.MockTransport(
        lambda r: httpx.Response(200, json={"access_token": "tok", "expires_in": 900, "user_id": "u", "full_name": "М"})))
    monkeypatch.setattr(platform, "transport", httpx.MockTransport(services))
    ctx = SimpleNamespace(headers={"authorization": "Bearer tm_good"})
    module = "11111111-1111-1111-1111-111111111111"

    created = await tools.create_test(ctx, tools.TestFields(
        title="Практическая работа 1", grade_level=7, module_id=module, shared=True, time_mode="total", time_limit_min=20,
        items=[tools.TestItem(task="(100345)", points=2), tools.TestItem(task="100346")],
    ))
    body = sent[-1][2]
    assert [i["task_id"] for i in body["items"]] == ["t100345", "t100346"] and body["items"][0]["points"] == 2
    assert (body["module_id"], body["shared"], body["time_limit_s"]) == (module, True, 1200)
    assert created["module"]["title"] == "Миссия 1" and created["shared"] is True

    # Правка частями: заголовок поменялся, состав, привязка и таймер — прежние.
    await tools.update_test(ctx, "22222222-2222-2222-2222-222222222222", {"title": "Практическая работа №1"})
    body = sent[-1][2]
    assert sent[-1][0] == "PUT" and body["title"] == "Практическая работа №1"
    assert (body["module_id"], body["shared"], body["time_limit_s"]) == (module, True, 1200)
    assert [i["task_id"] for i in body["items"]] == ["t100345", "t100346"]
    with pytest.raises(ToolError, match="Неизвестные поля: theme"):
        await tools.update_test(ctx, "22222222-2222-2222-2222-222222222222", {"theme": "comics"})


async def test_key_in_url_and_hidden_in_logs():
    """Ключ в адресе коннектора (у «своего коннектора» Claude нет заголовков): /tm_… → Authorization; в журнале — tm_***."""
    import logging

    from app.main import HideKeys, KeyInPath

    seen: list[dict] = []

    async def inner(scope, receive, send):
        seen.append(scope)

    app = KeyInPath(inner)
    await app({"type": "http", "path": "/tm_Abc-1_x", "raw_path": b"/tm_Abc-1_x", "headers": [(b"accept", b"*/*")]}, None, None)
    await app({"type": "http", "path": "/", "raw_path": b"/", "headers": [(b"authorization", b"Bearer tm_hdr")]}, None, None)
    await app({"type": "http", "path": "/health", "raw_path": b"/health", "headers": []}, None, None)
    assert seen[0]["path"] == "/" and dict(seen[0]["headers"])[b"authorization"] == b"Bearer tm_Abc-1_x"
    assert platform.api_key({k.decode(): v.decode() for k, v in seen[0]["headers"]}) == "tm_Abc-1_x"
    assert dict(seen[1]["headers"])[b"authorization"] == b"Bearer tm_hdr" and seen[2]["path"] == "/health"

    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', ("1.2.3.4", "POST", "/tm_Abc-1_x", "1.1", 200), None)
    HideKeys().filter(record)
    assert "tm_Abc" not in record.getMessage() and "/tm_***" in record.getMessage()


PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16).decode()


async def test_upload_images(platform_fake):
    """Картинки для Claude: base64 из файла (upload_image) и вшитые в текст data:image/… — в хранилище платформы."""
    from types import SimpleNamespace

    from app import tools

    assert platform.decode_image(f"data:image/png;base64,{PNG}")[1] == ".png"
    with pytest.raises(ToolError, match="не картинка"):
        platform.decode_image(base64.b64encode(b"<svg></svg>").decode())
    with pytest.raises(ToolError, match="base64"):
        platform.decode_image("это не base64!")

    text = f'Схема: ![сайт](data:image/png;base64,{PNG} "width=400") и ![граф](https://example.com/g.png)'
    out = await platform.localize_images("tm_good", text)
    assert out == 'Схема: ![сайт](/api/media/files/f2/content "width=400") и ![граф](/api/media/files/f1/content)'
    upload = next(c for c in platform_fake if c[1] == "/files")[2]["multipart"]
    assert b'name="purpose"' in upload and b"content" in upload and b'filename="' in upload

    ctx = SimpleNamespace(headers={"authorization": "Bearer tm_good"})
    res = await tools.upload_image(ctx, PNG, "Тэгги")
    assert res["markdown"] == "![Тэгги](/api/media/files/f2/content)" and res["url"].endswith("/api/media/files/f2/content")


async def test_course_changes_and_submit_tools(monkeypatch):
    """Черновик изменений курса, отправка на проверку, задачи в публичный банк (решение №46)."""
    from types import SimpleNamespace

    from app import tools

    sent: list[tuple[str, str]] = []
    draft = {"id": "d1", "title": "Вебоград", "status": "private", "can_edit": True, "revision_of": "c1", "revision": None,
             "sections": [{"id": "s1", "title": "Уровень 1", "modules": [{"id": "dm1", "title": "Миссия 1", "materials": [],
                                                                              "origin_id": "m1"}]}]}

    def services(request: httpx.Request) -> httpx.Response:
        sent.append((request.method, request.url.path))
        path = request.url.path
        if path == "/courses/c1/revision":
            return httpx.Response(201, json=draft)
        if path == "/courses/d1/submit":
            return httpx.Response(200, json=draft | {"status": "pending"})
        if path == "/tasks" and request.method == "GET":
            n = int(request.url.params["q"])
            return httpx.Response(200, json={"items": [{"id": f"t{n}", "number": n}], "total": 1})
        if path.startswith("/tasks/") and path.endswith("/submit"):
            tid = path.split("/")[2]
            if tid == "t100002":
                return httpx.Response(422, json={"error": {"code": "topic_required", "message": "Выберите тему"}})
            return httpx.Response(200, json={"id": tid, "number": int(tid[1:]), "title": "З", "type": "short", "difficulty": 1,
                                             "status": "pending", "topic_path": []})
        if path.startswith("/tasks/"):
            tid = path.rsplit("/", 1)[1]
            return httpx.Response(200, json={"id": tid, "number": int(tid[1:]), "title": "З"})
        return httpx.Response(404, json={"error": {"code": "not_found", "message": "Нет"}})

    platform._tokens.clear()
    monkeypatch.setattr(platform.identity, "transport", httpx.MockTransport(
        lambda r: httpx.Response(200, json={"access_token": "tok", "expires_in": 900, "user_id": "u", "full_name": "М"})))
    monkeypatch.setattr(platform, "transport", httpx.MockTransport(services))
    ctx = SimpleNamespace(headers={"authorization": "Bearer tm_good"})

    out = await tools.start_course_changes(ctx, "c1")
    assert out["draft_of_course_id"] == "c1" and out["sections"][0]["modules"][0]["published_module_id"] == "m1"
    assert (await tools.submit_course(ctx, "d1"))["status"] == "pending"
    res = await tools.submit_tasks_to_bank(ctx, ["100001", "(100002)"])
    assert [t["number"] for t in res["sent"]] == [100001] and res["failed"] == [{"task": "(100002)", "error": "Выберите тему"}]
    assert ("POST", "/tasks/t100001/submit") in sent
