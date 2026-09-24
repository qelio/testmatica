import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from .config import settings

_hasher = PasswordHasher()
# Хэш для сравнения, когда пользователь не найден: время ответа не выдаёт, существует ли аккаунт.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def generate_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def hash_code(code: str) -> str:
    return hmac.new(settings.secret_key.encode(), code.encode(), hashlib.sha256).hexdigest()


def codes_equal(code_hash: str, code: str) -> bool:
    return hmac.compare_digest(code_hash, hash_code(code))


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    visible = name[:2] if len(name) > 2 else name[:1]
    return f"{visible}***@{domain}"
