from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "mcp"
    database_url: str = ""  # своей базы нет: всё — через API других сервисов от имени пользователя
    identity_url: str = "http://identity:8000"
    assessment_url: str = "http://assessment:8000"
    content_url: str = "http://content:8000"
    media_url: str = "http://media:8000"
    # Адрес сайта — для ссылок на созданные материалы и проверки заголовка Host.
    web_base_url: str = "http://localhost:8080"
    allowed_hosts: str = "localhost:*,127.0.0.1:*,mcp:*"


settings = Settings()
