from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "whiteboard"

    redis_url: str = "redis://redis:6379/0"
    schedule_url: str = "http://schedule:8000"
    classroom_url: str = "http://classroom:8000"
    # Сколько секунд ждать сообщение авторизации после открытия WebSocket.
    ws_auth_timeout: float = 5
    max_items: int = 20000  # объектов на доске
    max_item_bytes: int = 256 * 1024  # один объект (штрих, картинка, текст) в JSON
    max_batch: int = 500  # объектов в одной правке


settings = Settings()
