"""Внутренние (сервис-сервис) вызовы REST.

Внутренние эндпоинты живут под /internal/..., наружу через Traefik не публикуются
и дополнительно защищены общим токеном в заголовке X-Internal-Token.
"""

import hmac
from typing import Any

import httpx
from fastapi import Header

from .errors import ApiError

INTERNAL_HEADER = "X-Internal-Token"


def internal_guard(token: str):
    """FastAPI-зависимость для внутренних эндпоинтов."""

    async def dependency(x_internal_token: str | None = Header(None)) -> None:
        if not x_internal_token or not hmac.compare_digest(x_internal_token, token):
            raise ApiError(403, "forbidden", "Внутренний эндпоинт")

    return dependency


class InternalClient:
    """HTTP-клиент к другому сервису. Ошибки 4xx пробрасываются как ApiError с тем же кодом,
    чтобы пользователь увидел понятное сообщение; недоступность сервиса — 503."""

    def __init__(self, base_url: str, token: str, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.transport: httpx.AsyncBaseTransport | None = None  # подменяется в тестах

    async def request(self, method: str, path: str, **kwargs) -> Any:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={INTERNAL_HEADER: self.token},
            transport=self.transport,
        ) as client:
            try:
                resp = await client.request(method, path, **kwargs)
            except httpx.HTTPError:
                raise ApiError(503, "service_unavailable", "Сервис временно недоступен, попробуйте позже") from None
        if resp.status_code >= 500:
            raise ApiError(503, "service_unavailable", "Сервис временно недоступен, попробуйте позже")
        if resp.status_code >= 400:
            error = (resp.json() if resp.content else {}).get("error", {})
            raise ApiError(
                resp.status_code,
                error.get("code", "upstream_error"),
                error.get("message", "Ошибка запроса"),
                error.get("details"),
            )
        return resp.json() if resp.content else None

    async def get(self, path: str, **kwargs) -> Any:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> Any:
        return await self.request("POST", path, **kwargs)

    async def patch(self, path: str, **kwargs) -> Any:
        return await self.request("PATCH", path, **kwargs)
