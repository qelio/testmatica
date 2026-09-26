from testmatica_common.auth import Auth, TokenVerifier
from testmatica_common.db import Database
from testmatica_common.messaging import Outbox

from .config import settings

db = Database(settings.database_url)
auth = Auth(TokenVerifier(settings.jwt_issuer, settings.jwt_audience, jwks_url=settings.jwks_url))
outbox = Outbox(producer=settings.service_name)
