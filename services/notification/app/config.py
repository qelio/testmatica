from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "notification"

    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = False
    # false — почтового сервера пока нет (решение №29): письма не отправляются, только пишется в лог.
    email_enabled: bool = True
    mail_from: str = "ТестМатика <no-reply@testmatica.local>"


settings = Settings()
