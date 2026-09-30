#!/bin/sh
# Выкладка версии на сервере (/opt/testmatica): вход в реестр по токену сервисного аккаунта ВМ,
# загрузка образов, перезапуск изменившихся контейнеров. Миграции БД сервисы применяют сами при старте.
#   sh deploy.sh <тег образов>      — обычно запускает GitHub Actions
set -eu
cd "$(dirname "$0")"
TAG="${1:?укажите тег образов}"

TOKEN=$(curl -sf -H "Metadata-Flavor: Google" \
  http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])')
echo "$TOKEN" | docker login --username iam --password-stdin cr.yandex >/dev/null

# Тег версии — в .env, чтобы ручной «docker compose up» запускал ту же версию.
sed -i "s/^TAG=.*/TAG=$TAG/" .env

docker compose -f compose.prod.yaml pull --quiet
docker compose -f compose.prod.yaml up -d --remove-orphans
docker image prune -f >/dev/null
docker compose -f compose.prod.yaml ps --format 'table {{.Service}}\t{{.Status}}'
