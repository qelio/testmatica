from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "moderation"


settings = Settings()
