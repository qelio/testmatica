from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "identity"

    redis_url: str = "redis://redis:6379/0"
    media_url: str = "http://media:8000"
    # Секрет для HMAC одноразовых кодов. В проде — из секретов облака.
    secret_key: str

    jwt_private_key_path: str = "/keys/jwt_private.pem"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_days: int = 30
    refresh_cookie_name: str = "tm_refresh"
    # Путь, как его видит браузер (Traefik добавляет префикс /api/identity).
    refresh_cookie_path: str = "/api/identity/auth"
    refresh_cookie_secure: bool = False

    otp_ttl_seconds: int = 600
    otp_max_attempts: int = 5
    otp_resend_interval_seconds: int = 60

    login_lock_seconds: int = 900
    ip_max_login_failures: int = 200  # за login_lock_seconds; класс за одним школьным адресом

    web_base_url: str = "http://localhost:8080"
    # Письма с кодами (подтверждение email, вход с кодом, сброс пароля, смена email). false — почтового
    # сервера пока нет (решение №29): регистрация без подтверждения, вход без кода, остальное — «скоро».
    email_codes: bool = True


settings = Settings()
