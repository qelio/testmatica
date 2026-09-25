# Песочница: отдельный минимальный образ, запускается от nobody без привилегий.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements.txt
ARG DEV=0
RUN if [ "$DEV" = "1" ]; then pip install -r requirements-dev.txt; fi
COPY app ./app
COPY tests ./tests

USER 65534:65534
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
