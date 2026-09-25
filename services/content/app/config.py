from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "content"

    media_url: str = "http://media:8000"
    classroom_url: str = "http://classroom:8000"


settings = Settings()
