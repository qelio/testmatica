from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "classroom"
    content_url: str = "http://content:8000"

    identity_url: str = "http://identity:8000"
    web_base_url: str = "http://localhost:8080"
    invitation_ttl_days: int = 14


settings = Settings()
