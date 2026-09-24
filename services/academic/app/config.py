from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "academic"

    schedule_url: str = "http://schedule:8000"
    classroom_url: str = "http://classroom:8000"


settings = Settings()
