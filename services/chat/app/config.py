from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "chat"

    redis_url: str = "redis://redis:6379/0"
    media_url: str = "http://media:8000"
    billing_url: str = "http://billing:8000"
    max_attachments: int = 10
    message_max_length: int = 4000
    # Сколько секунд ждать сообщение авторизации после открытия WebSocket.
    ws_auth_timeout: float = 5


settings = Settings()
