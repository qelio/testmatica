from testmatica_common.auth import Auth, TokenVerifier
from testmatica_common.db import Database
from testmatica_common.internal import InternalClient
from testmatica_common.messaging import Outbox
from testmatica_common.plans import Plans

from .config import settings

db = Database(settings.database_url)
auth = Auth(TokenVerifier(settings.jwt_issuer, settings.jwt_audience, jwks_url=settings.jwks_url))
outbox = Outbox(producer=settings.service_name)
schedule = InternalClient(settings.schedule_url, settings.internal_token)
classroom = InternalClient(settings.classroom_url, settings.internal_token)
assessment = InternalClient(settings.assessment_url, settings.internal_token)
billing = InternalClient(settings.billing_url, settings.internal_token)
plans = Plans(billing)
