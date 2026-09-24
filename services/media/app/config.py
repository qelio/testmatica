from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "media"

    # Сервер работает с хранилищем по внутреннему адресу, а ссылки для браузера
    # подписываются публичным адресом (локально — localhost, в облаке — Yandex Object Storage).
    s3_endpoint: str = "http://s3:8333"
    s3_public_endpoint: str = "http://localhost:8333"
    s3_region: str = "ru-central1"
    s3_access_key: str = "dev"
    s3_secret_key: str = "dev"
    s3_bucket: str = "testmatica"

    # Срок жизни ссылки на скачивание.
    url_ttl_seconds: int = 3600


settings = Settings()
