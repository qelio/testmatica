#!/bin/bash
# Создаёт для каждого сервиса отдельного пользователя и две базы: <svc> и <svc>_test.
# Запускается автоматически при первом старте PostgreSQL; повторный запуск безопасен:
#   make db-init
set -euo pipefail

for svc in ${SERVICE_DATABASES}; do
  echo "init database for service: ${svc}"
  psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname postgres <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${svc}') THEN
    CREATE ROLE ${svc} LOGIN PASSWORD '${svc}_dev';
  END IF;
END
\$\$;
SELECT 'CREATE DATABASE ${svc} OWNER ${svc}' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${svc}')\gexec
SELECT 'CREATE DATABASE ${svc}_test OWNER ${svc}' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${svc}_test')\gexec
REVOKE ALL ON DATABASE ${svc} FROM PUBLIC;
REVOKE ALL ON DATABASE ${svc}_test FROM PUBLIC;
SQL
done
