from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "marketplace"

    identity_url: str = "http://identity:8000"
    media_url: str = "http://media:8000"
    content_url: str = "http://content:8000"
    web_base_url: str = "http://localhost:8080"

    # Онлайн-статус: сессия продлевается примерно раз в 15 минут, пока человек на сайте.
    online_window_minutes: int = 20


settings = Settings()
