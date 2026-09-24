from redis.asyncio import Redis
from testmatica_common.auth import Auth, TokenVerifier
from testmatica_common.db import Database
from testmatica_common.messaging import Outbox

from .config import settings

db = Database(settings.database_url)
redis = Redis.from_url(settings.redis_url, decode_responses=True)
verifier = TokenVerifier(settings.jwt_issuer, settings.jwt_audience, jwks_url=settings.jwks_url)
auth = Auth(verifier)
outbox = Outbox(producer=settings.service_name)
