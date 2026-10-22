"""Защита от перебора паролей: счётчик неудачных входов в Redis по IP.

Аккаунт после неверных паролей не блокируется: дети ошибаются в пароле, а блокировка запирала их (и её мог
устроить кто угодно, зная логин). Порог по IP — с запасом на класс за одним школьным адресом."""

from testmatica_common.errors import ApiError

from .config import settings
from .deps import redis


def _ip_key(ip: str) -> str:
    return f"login:fail:ip:{ip}"


async def check_login_allowed(ip: str) -> None:
    if int(await redis.get(_ip_key(ip)) or 0) >= settings.ip_max_login_failures:
        ttl = await redis.ttl(_ip_key(ip))
        raise ApiError(429, "too_many_requests", "Слишком много попыток входа с вашего адреса. Попробуйте чуть позже.",
                       {"retry_after": max(ttl, 1)})


async def register_login_failure(ip: str) -> None:
    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr(_ip_key(ip))
        pipe.expire(_ip_key(ip), settings.login_lock_seconds, nx=True)
        await pipe.execute()
