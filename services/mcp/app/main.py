"""Сервис mcp (решение №41): подключение Claude к ТестМатике по протоколу MCP (Streamable HTTP).

Снаружи — https://testmatica.ru/api/mcp; ключ доступа педагога — в заголовке Authorization: Bearer tm_…
Своей базы и очередей нет: функции (app/tools.py) вызывают API других сервисов от имени владельца ключа."""

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


hosts = [h.strip() for h in settings.allowed_hosts.split(",") if h.strip()]
app = mcp.streamable_http_app(
    streamable_http_path="/",
    # Каждый вызов самостоятелен: ключ приходит в каждом запросе, состояние между запросами не нужно.
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=["https://claude.ai", *[f"https://{h}" for h in hosts], *[f"http://{h}" for h in hosts]],
    ),
)
