"""Личные ключи доступа (решение №41): Claude Desktop и другие программы работают с платформой от имени пользователя.

Ключ «tm_…» обменивается на обычный access-токен (internal), поэтому права те же, что в интерфейсе:
что может пользователь — то может и ключ. Хранится только sha256; ключ показывается один раз."""

import hashlib
import secrets

PREFIX = "tm_"
MAX_KEYS = 10
ALLOWED_ROLES = {"teacher", "moderator", "admin"}  # материалы создают педагоги


def generate() -> str:
    return PREFIX + secrets.token_urlsafe(30)


def digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()
