from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "video"

    schedule_url: str = "http://schedule:8000"

    # LiveKit: внутренний адрес API и адрес, который получает браузер.
    livekit_url: str = "http://livekit:7880"
    livekit_public_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "dev-secret-change-me-dev-secret-change-me"

    # Записи: своя корзина в S3 (её же указывает конфиг egress).
    s3_endpoint: str = "http://s3:8333"
    s3_public_endpoint: str = "http://localhost:8333"
    s3_region: str = "ru-central1"
    s3_access_key: str = "dev"
    s3_secret_key: str = "dev"
    s3_bucket: str = "recordings"
    url_ttl_seconds: int = 3600

    # Когда можно войти в комнату: педагог — за 30 минут, ученик — за 15; все — до 30 минут после конца.
    billing_url: str = "http://billing:8000"
    teacher_join_before_min: int = 30
    student_join_before_min: int = 15
    join_after_end_min: int = 30
    # Бесплатный тариф (ТЗ, решения №4–5): занятие до 40 минут, предупреждение за 5;
    # записи хранятся 14 дней, не больше 3 у педагога (четвёртая вытесняет самую старую).
    free_time_limit_min: int = 40
    free_recordings_keep: int = 3
    free_recording_days: int = 14
    # Тариф «Базовый»: без лимита времени и количества записей, хранение 30 дней.
    basic_recording_days: int = 30
    # Ёмкость комнат (ТЗ, раздел 7).
    individual_capacity: int = 2
    group_capacity: int = 16


settings = Settings()
