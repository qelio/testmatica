"""Защита от перебора паролей: счётчики неудачных входов в Redis по логину и по IP."""

from testmatica_common.errors import ApiError

from .config import settings
from .deps import redis


def _user_key(identifier: str) -> str:
    return f"login:fail:user:{identifier}"


def _ip_key(ip: str) -> str:
    return f"login:fail:ip:{ip}"


async def check_login_allowed(identifier: str, ip: str) -> None:
    user_fails, ip_fails = await redis.mget(_user_key(identifier), _ip_key(ip))
    if int(user_fails or 0) >= settings.login_max_failures:
        ttl = await redis.ttl(_user_key(identifier))
        raise ApiError(
            429,
            "account_locked",
            "Слишком много неудачных попыток входа. Попробуйте позже.",
            {"retry_after": max(ttl, 1)},
        )
    if int(ip_fails or 0) >= settings.ip_max_login_failures:
        raise ApiError(429, "too_many_requests", "Слишком много попыток входа с вашего адреса.")


async def register_login_failure(identifier: str, ip: str) -> None:
    async with redis.pipeline(transaction=True) as pipe:
        for key in (_user_key(identifier), _ip_key(ip)):
            pipe.incr(key)
            pipe.expire(key, settings.login_lock_seconds, nx=True)
        await pipe.execute()


async def reset_login_failures(identifier: str) -> None:
    await redis.delete(_user_key(identifier))
