# Общий образ для всех Python-сервисов.
# Контекст сборки — корень репозитория; сервис задаётся аргументом SERVICE.
#   docker build -f infra/docker/python-service.Dockerfile --build-arg SERVICE=identity .
FROM python:3.13-slim

ARG SERVICE
ARG DEV=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Шрифты с кириллицей для PDF (карточки учеников, выгрузки аналитики): DejaVu и округлый Comfortaa.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core fonts-comfortaa \
    && rm -rf /var/lib/apt/lists/*

COPY libs/platform-common /libs/platform-common
RUN pip install -e /libs/platform-common

COPY services/${SERVICE}/requirements.txt services/${SERVICE}/requirements-dev.txt ./
RUN pip install -r requirements.txt \
    && if [ "$DEV" = "1" ]; then pip install -r requirements-dev.txt; fi

COPY services/${SERVICE} /app

# Непривилегированный пользователь.
RUN useradd --create-home --uid 1000 app && mkdir -p /keys && chown app /keys
USER app

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
