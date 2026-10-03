#!/bin/sh
# Боевой PostgreSQL на ВМ (решение №38): для каждого сервиса — своя база и свой пользователь с паролем из .env
# (PG_PASSWORD_<СЕРВИС>, те же, что были в Managed PostgreSQL). Запускается один раз — при первом старте с пустым томом.
set -eu

for svc in ${SERVICE_DATABASES}; do
  var="PG_PASSWORD_$(echo "$svc" | tr '[:lower:]' '[:upper:]')"
  password=$(eval "printf '%s' \"\${$var:?нет пароля $var}\"")
  echo "init database for service: ${svc}"
  psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname postgres <<SQL
CREATE ROLE ${svc} LOGIN PASSWORD '${password}' CONNECTION LIMIT 30;
CREATE DATABASE ${svc} OWNER ${svc};
REVOKE ALL ON DATABASE ${svc} FROM PUBLIC;
SQL
done

# Расширения, которые нужны миграциям (сервис не может включить их сам).
psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname schedule -c "CREATE EXTENSION IF NOT EXISTS btree_gist"
