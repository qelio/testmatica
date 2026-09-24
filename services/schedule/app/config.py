from testmatica_common.config import CommonSettings


class Settings(CommonSettings):
    service_name: str = "schedule"

    classroom_url: str = "http://classroom:8000"

    # Серия занятий: не больше этого числа занятий и не дальше года вперёд.
    series_max_lessons: int = 200
    series_max_days: int = 366

    # За сколько часов до начала напоминать о занятии.
    reminder_hours: tuple[int, ...] = (24, 2)
    jobs_interval_seconds: float = 30


settings = Settings()
