from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "assessment"

    code_runner_url: str = "http://code-runner:8000"
    media_url: str = "http://media:8000"
    classroom_url: str = "http://classroom:8000"
    content_url: str = "http://content:8000"
    schedule_url: str = "http://schedule:8000"

    # Не чаще одной отправки кода в N секунд от одного ученика — песочница общая.
    code_submit_interval_seconds: float = 3
    # Разбор решения открывается после верного ответа или после стольких попыток.
    explanation_after_attempts: int = 3


settings = Settings()
