from pydantic_settings import BaseSettings, SettingsConfigDict


class CommonSettings(BaseSettings):
    """Настройки, общие для всех сервисов. Значения берутся из переменных окружения."""

    model_config = SettingsConfigDict(extra="ignore")

    service_name: str
    environment: str = "dev"
    log_level: str = "INFO"
    # Префикс, под которым сервис виден снаружи через Traefik (например, /api/identity).
    # Нужен для корректных ссылок в Swagger; маршруты внутри сервиса от него не зависят.
    root_path: str = ""

    database_url: str
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"

    jwks_url: str = "http://identity:8000/.well-known/jwks.json"
    jwt_issuer: str = "testmatica-identity"
    jwt_audience: str = "testmatica"

    # Outbox relay и consumers. В тестах выключаются.
    run_background: bool = True
