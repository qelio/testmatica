"""Сервис mcp: ключ из заголовка, обмен на токен, ошибки сервисов, перенос картинок (решение №41)."""

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
