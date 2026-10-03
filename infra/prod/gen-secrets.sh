#!/bin/sh
# Случайные секреты для .env боевого окружения. Запускать один раз; вывод дописать в .env.
#   sh infra/prod/gen-secrets.sh >> .env
set -eu
rnd() { openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c "$1"; }
echo "INTERNAL_TOKEN=$(rnd 48)"
echo "IDENTITY_SECRET_KEY=$(rnd 64)"
echo "RABBITMQ_PASSWORD=$(rnd 32)"
echo "LIVEKIT_API_KEY=API$(rnd 12)"
echo "LIVEKIT_API_SECRET=$(rnd 48)"
# PostgreSQL на ВМ: администратор и по пользователю на сервис.
echo "PG_ADMIN_PASSWORD=$(rnd 32)"
for svc in IDENTITY NOTIFICATION AUDIT CLASSROOM SCHEDULE ACADEMIC CHAT MEDIA CONTENT MODERATION ASSESSMENT MARKETPLACE BILLING VIDEO; do
  echo "PG_PASSWORD_${svc}=$(rnd 32)"
done
