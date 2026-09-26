"""Проверка JWT, выданных сервисом identity, и зависимости FastAPI для прав доступа."""

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .errors import ApiError

ROLE_STUDENT = "student"
ROLE_TEACHER = "teacher"
ROLE_MODERATOR = "moderator"
ROLE_ADMIN = "admin"


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    roles: frozenset[str]

    def has_any(self, *roles: str) -> bool:
        # Администратор имеет все права модератора (ТЗ, раздел 2).
        effective = set(self.roles)
        if ROLE_ADMIN in effective:
            effective.add(ROLE_MODERATOR)
        return bool(effective.intersection(roles))


class TokenVerifier:
    """Проверяет подпись access-токена по JWKS.

    Ключи берутся либо из static_jwks (сам identity), либо скачиваются по jwks_url и кэшируются.
    Неизвестный kid вызывает повторную загрузку — так переживается ротация ключей.
    """

    def __init__(
        self,
        issuer: str,
        audience: str,
        jwks_url: str | None = None,
        static_jwks: dict[str, Any] | None = None,
        cache_ttl: int = 300,
    ) -> None:
        self.issuer = issuer
        self.audience = audience
        self.jwks_url = jwks_url
        self.cache_ttl = cache_ttl
        self._keys: dict[str, Any] = {}
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()
        if static_jwks is not None:
            self._load(static_jwks)
            self._fetched_at = float("inf")

    def _load(self, jwks: dict[str, Any]) -> None:
        self._keys = {k["kid"]: jwt.PyJWK(k).key for k in jwks.get("keys", [])}

    async def _refresh(self, force: bool = False) -> None:
        if self.jwks_url is None:
            return
        async with self._lock:
            if not force and time.monotonic() - self._fetched_at < self.cache_ttl:
                return
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(self.jwks_url)
                resp.raise_for_status()
            self._load(resp.json())
            self._fetched_at = time.monotonic()

    async def _key(self, kid: str) -> Any:
        if time.monotonic() - self._fetched_at >= self.cache_ttl:
            await self._refresh()
        if kid not in self._keys:
            await self._refresh(force=True)
        if kid not in self._keys:
            raise jwt.InvalidTokenError("unknown kid")
        return self._keys[kid]

    async def verify(self, token: str) -> dict[str, Any]:
        header = jwt.get_unverified_header(token)
        key = await self._key(header.get("kid", ""))
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=self.audience,
            issuer=self.issuer,
            options={"require": ["exp", "sub", "iat"]},
        )


_bearer = HTTPBearer(auto_error=False)


class Auth:
    """Зависимости FastAPI:

        auth = Auth(verifier)
        @app.get("/x")
        async def x(user: Principal = Depends(auth.principal)): ...
        @app.get("/admin", dependencies=[Depends(auth.require(ROLE_ADMIN))]): ...
    """

    def __init__(self, verifier: TokenVerifier) -> None:
        self.verifier = verifier

    async def principal(
        self, creds: HTTPAuthorizationCredentials | None = Depends(_bearer)
    ) -> Principal:
        if creds is None:
            raise ApiError(401, "unauthorized", "Требуется авторизация")
        try:
            claims = await self.verifier.verify(creds.credentials)
        except (jwt.InvalidTokenError, httpx.HTTPError):
            raise ApiError(401, "invalid_token", "Недействительный или просроченный токен") from None
        if claims.get("typ") != "access":
            raise ApiError(401, "invalid_token", "Недействительный токен")
        return Principal(
            user_id=UUID(claims["sub"]),
            roles=frozenset(claims.get("roles", [])),
        )

    async def optional(
        self, creds: HTTPAuthorizationCredentials | None = Depends(_bearer)
    ) -> Principal | None:
        """Для страниц, доступных и без входа (публичная библиотека): None — гость.
        Если токен передан, но недействителен — 401, чтобы клиент обновил его, а не получил «гостевой» ответ."""
        if creds is None:
            return None
        return await self.principal(creds)

    def require(self, *roles: str):
        async def dependency(principal: Principal = Depends(self.principal)) -> Principal:
            if not principal.has_any(*roles):
                raise ApiError(403, "forbidden", "Недостаточно прав")
            return principal

        return dependency
