"""Общие объекты сервиса. Создаются один раз при импорте."""

from redis.asyncio import Redis
from testmatica_common.auth import Auth, TokenVerifier
from testmatica_common.db import Database
from testmatica_common.internal import InternalClient
from testmatica_common.messaging import Outbox

from .config import settings
from .tokens import TokenIssuer, load_or_create_key

db = Database(settings.database_url)
redis = Redis.from_url(settings.redis_url, decode_responses=True)
outbox = Outbox(producer=settings.service_name)

signing_key = load_or_create_key(settings.jwt_private_key_path)
issuer = TokenIssuer(signing_key, settings)
# identity проверяет свои же токены локальным ключом, без HTTP-запроса к себе.
auth = Auth(
    TokenVerifier(settings.jwt_issuer, settings.jwt_audience, static_jwks=signing_key.jwks)
)
media = InternalClient(settings.media_url, settings.internal_token)
