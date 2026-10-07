"""Доступ к платформе от имени пользователя (решение №41).

Claude присылает личный ключ «tm_…» в заголовке Authorization. Ключ обменивается в identity на обычный
access-токен пользователя (кэш — пока токен жив), и дальше сервис ходит в публичные API assessment, content
и media как сам пользователь: права, проверки и ошибки — те же, что в интерфейсе."""

import hashlib
import re
import time
from collections.abc import Mapping
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError
from testmatica_common.errors import ApiError
from testmatica_common.internal import InternalClient

from .config import settings

identity = InternalClient(settings.identity_url, settings.internal_token)
SERVICES = {"assessment": settings.assessment_url, "content": settings.content_url, "media": settings.media_url}
transport: httpx.AsyncBaseTransport | None = None  # подменяется в тестах

NO_KEY = ToolError(
    "Нет ключа доступа. В ТестМатике: Личный кабинет → «Подключение Claude» → «Выпустить ключ» и укажите в коннекторе "
    "Claude адрес с ключом: https://testmatica.ru/api/mcp/tm_… (его показывают сразу после выпуска ключа)."
)

_tokens: dict[str, tuple[str, float, str]] = {}  # sha256(ключ) → (токен, когда истекает, имя пользователя)


def api_key(headers: Mapping[str, str] | None) -> str:
    raw = (headers or {}).get("authorization") or (headers or {}).get("Authorization") or ""
    key = raw.removeprefix("Bearer ").removeprefix("bearer ").strip() or (headers or {}).get("x-api-key", "").strip()
    if not key.startswith("tm_"):
        raise NO_KEY
    return key


async def session_for(key: str) -> tuple[str, str]:
    """Токен пользователя и его имя; обмен в identity — не чаще, чем раз в жизнь токена."""
    digest = hashlib.sha256(key.encode()).hexdigest()
    cached = _tokens.get(digest)
    if cached and cached[1] > time.time() + 30:
        return cached[0], cached[2]
    try:
        out = await identity.post("/internal/api-keys/exchange", json={"key": key})
    except ApiError as e:
        if e.status in (401, 403):
            raise ToolError("Ключ доступа недействителен или отозван — выпустите новый в личном кабинете ТестМатики") from None
        raise ToolError(e.message) from None
    _tokens[digest] = (out["access_token"], time.time() + out["expires_in"], out["full_name"])
    return out["access_token"], out["full_name"]


def _error_text(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error", {})
    except ValueError:
        err = {}
    text = err.get("message") or f"Ошибка {resp.status_code}"
    fields = (err.get("details") or {}).get("fields") if isinstance(err.get("details"), dict) else None
    if fields:  # ошибки проверки полей — чтобы Claude мог исправить и повторить
        parts = []
        for f in fields:
            msg = str(f.get("message", "")).removeprefix("Value error, ")
            parts.append(f"{f['field']}: {msg}" if f.get("field") else msg)
        text += ": " + "; ".join(parts)
    return text


async def call(key: str, service: str, method: str, path: str, **kwargs) -> Any:
    token, _ = await session_for(key)
    async with httpx.AsyncClient(base_url=SERVICES[service], timeout=30, transport=transport) as client:
        try:
            resp = await client.request(method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs)
        except httpx.HTTPError:
            raise ToolError("Сервис ТестМатики временно недоступен, попробуйте позже") from None
    if resp.status_code >= 500:
        raise ToolError("Сервис ТестМатики временно недоступен, попробуйте позже")
    if resp.status_code >= 400:
        raise ToolError(_error_text(resp))
    return resp.json() if resp.content else None


def link(path: str) -> str:
    return f"{settings.web_base_url.rstrip('/')}{path}"


# ---------- картинки из интернета → в хранилище платформы ----------

IMAGE = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)((?:\s+\"[^\"]*\")?)\)")


async def localize_images(key: str, text: str) -> str:
    """Картинки по внешним ссылкам переносятся в хранилище платформы (как вставка в редакторе):
    чужая ссылка со временем ломается. Не удалось — ссылка остаётся как есть."""
    if not text or "](http" not in text:
        return text
    cache: dict[str, str] = {}
    for m in IMAGE.finditer(text):
        url = m.group(2)
        if url in cache or url.startswith(settings.web_base_url):
            continue
        try:
            stored = await call(key, "media", "POST", "/files/import", json={"url": url})
            cache[url] = f"/api/media/files/{stored['id']}/content"
        except ToolError:
            cache[url] = url
    return IMAGE.sub(lambda m: f"![{m.group(1)}]({cache.get(m.group(2), m.group(2))}{m.group(3)})", text)
