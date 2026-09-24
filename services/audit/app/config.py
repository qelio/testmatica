from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "audit"


settings = Settings()
