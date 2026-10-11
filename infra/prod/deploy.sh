#!/bin/sh
# Выкладка версии на сервере (/opt/testmatica): вход в реестр образов, загрузка образов, перезапуск изменившихся
# контейнеров. Миграции БД сервисы применяют сами при старте.
#   printf '%s' "$TOKEN" | sh deploy.sh <тег образов> <пользователь GitHub>   — обычно запускает GitHub Actions
# Образы — в GitHub Container Registry (ghcr.io, решение №45); токен — временный токен задания GitHub Actions,
# приходит через stdin (не виден в списке процессов) и живёт, пока идёт выкладка.
set -eu
cd "$(dirname "$0")"
TAG="${1:?укажите тег образов}"
REGISTRY_USER="${2:?укажите пользователя GitHub}"

docker login ghcr.io --username "$REGISTRY_USER" --password-stdin >/dev/null

# Тег версии — в .env, чтобы ручной «docker compose up» запускал ту же версию.
sed -i "s/^TAG=.*/TAG=$TAG/" .env

# Каждая выкладка приносит новые образы всех сервисов — старые версии удаляем (кроме запущенных),
# иначе диск ВМ заполняется за несколько выкладок. Откат — по тегу из реестра.
docker image prune -af >/dev/null
docker compose -f compose.prod.yaml pull
docker compose -f compose.prod.yaml up -d --remove-orphans
docker image prune -af >/dev/null
docker compose -f compose.prod.yaml ps --format 'table {{.Service}}\t{{.Status}}'
docker logout ghcr.io >/dev/null
