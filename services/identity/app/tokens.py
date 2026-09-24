import base64
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from testmatica_common.ids import uuid7

from .config import Settings
from .models import User


class SigningKey:
    def __init__(self, private_pem: bytes) -> None:
        self.private_key = serialization.load_pem_private_key(private_pem, password=None)
        jwk: dict[str, Any] = json.loads(RSAAlgorithm.to_jwk(self.private_key.public_key()))
        # kid — отпечаток ключа по RFC 7638.
        canonical = json.dumps({"e": jwk["e"], "kty": "RSA", "n": jwk["n"]}, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode()).digest()
        self.kid = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        self.jwks = {"keys": [{**jwk, "kid": self.kid, "use": "sig", "alg": "RS256"}]}


def load_or_create_key(path: str) -> SigningKey:
    """Локально ключ создаётся при первом запуске. В облаке файл монтируется из секретов."""
    key_path = Path(path)
    if not key_path.exists():
        key_path.parent.mkdir(parents=True, exist_ok=True)
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(pem)
    return SigningKey(key_path.read_bytes())


class TokenIssuer:
    def __init__(self, key: SigningKey, settings: Settings) -> None:
        self.key = key
        self.settings = settings

    def access_token(self, user: User) -> str:
        now = int(time.time())
        claims = {
            "iss": self.settings.jwt_issuer,
            "aud": self.settings.jwt_audience,
            "sub": str(user.id),
            "iat": now,
            "exp": now + self.settings.access_token_ttl_seconds,
            "jti": uuid7().hex,
            "typ": "access",
            "roles": user.role_names,
            "teacher_mode": user.teacher_mode,
        }
        return jwt.encode(claims, self.key.private_key, algorithm="RS256", headers={"kid": self.key.kid})
