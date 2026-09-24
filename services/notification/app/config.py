from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "notification"

    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = False
    mail_from: str = "Тестматика <no-reply@testmatica.local>"


settings = Settings()
