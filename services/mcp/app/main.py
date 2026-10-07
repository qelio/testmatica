"""Сервис mcp (решение №41): подключение Claude к ТестМатике по протоколу MCP (Streamable HTTP).

Снаружи — https://testmatica.ru/api/mcp/tm_… (ключ в адресе: в «своём коннекторе» Claude указывается только адрес)
или https://testmatica.ru/api/mcp с заголовком Authorization: Bearer tm_….
Своей базы и очередей нет: функции (app/tools.py) вызывают API других сервисов от имени владельца ключа."""

import logging
import re

from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from testmatica_common.logging import configure_logging

from .config import settings
from .tools import mcp

configure_logging(settings.service_name, settings.log_level)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


# Ключ в адресе: /tm_… → заголовок Authorization, путь — «/». В журнал ключ не попадает.
KEY_IN_PATH = re.compile(r"^/(tm_[A-Za-z0-9_-]+)/?$")
KEY = re.compile(r"tm_[A-Za-z0-9_-]+")


class KeyInPath:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and (m := KEY_IN_PATH.match(scope["path"])):
            headers = [(k, v) for k, v in scope["headers"] if k != b"authorization"]
            scope = dict(scope, path="/", raw_path=b"/", headers=[*headers, (b"authorization", f"Bearer {m.group(1)}".encode())])
        await self.app(scope, receive, send)


class HideKeys(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(KEY.sub("tm_***", a) if isinstance(a, str) else a for a in record.args)
        if isinstance(record.msg, str):
            record.msg = KEY.sub("tm_***", record.msg)
        return True


logging.getLogger("uvicorn.access").addFilter(HideKeys())

hosts = [h.strip() for h in settings.allowed_hosts.split(",") if h.strip()]
app = KeyInPath(mcp.streamable_http_app(
    streamable_http_path="/",
    # Каждый вызов самостоятелен: ключ приходит в каждом запросе, состояние между запросами не нужно.
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=["https://claude.ai", *[f"https://{h}" for h in hosts], *[f"http://{h}" for h in hosts]],
    ),
))
