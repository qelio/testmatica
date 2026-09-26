"""Помощники для тестов сервисов: выпуск JWT без сервиса identity и сборка событий."""

import json
import time
from datetime import UTC, datetime
from uuid import UUID

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from .auth import TokenVerifier
from .ids import uuid7
from .messaging import Envelope


class TestTokens:
    """Ключ и JWKS для тестов. Подменяет проверку токенов в сервисе:
    auth.verifier = tokens.verifier(settings)"""

    __test__ = False  # чтобы pytest не принимал класс за набор тестов

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(RSAAlgorithm.to_jwk(self.key.public_key()))
        self.jwks = {"keys": [{**jwk, "kid": "test", "alg": "RS256", "use": "sig"}]}

    def verifier(self, issuer: str, audience: str) -> TokenVerifier:
        return TokenVerifier(issuer, audience, static_jwks=self.jwks)

    def issue(
        self,
        user_id: UUID,
        roles: list[str],
        issuer: str,
        audience: str,
    ) -> str:
        now = int(time.time())
        claims = {
            "iss": issuer,
            "aud": audience,
            "sub": str(user_id),
            "iat": now,
            "exp": now + 300,
            "typ": "access",
            "roles": roles,
        }
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "test"})


def make_envelope(type: str, data: dict, producer: str = "test", actor_id: UUID | None = None) -> Envelope:
    return Envelope(
        event_id=uuid7(),
        type=type,
        occurred_at=datetime.now(UTC),
        producer=producer,
        actor_id=actor_id,
        data=data,
    )
