#!/bin/sh
# Резервная копия баз раз в сутки (решение №38): pg_dump каждой базы → локальный том (последние 7 дней)
# и Object Storage, s3://<бакет файлов>/backups/postgres/ (последние 30 дней). Раньше это делал Managed PostgreSQL.
#   Восстановление базы: pg_restore --clean --if-exists -d <svc> <svc>.dump (см. docs/deploy.md).
set -u

apk add --no-cache aws-cli >/dev/null 2>&1 || echo "aws-cli не установился — копии останутся только на диске ВМ"
export AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY}" AWS_SECRET_ACCESS_KEY="${S3_SECRET_KEY}" AWS_DEFAULT_REGION=ru-central1
S3="aws --endpoint-url=https://storage.yandexcloud.net s3"

backup() {
  day=$(date -u +%Y-%m-%d)
  dir="/backups/${day}"
  mkdir -p "${dir}"
  ok=1
  for svc in ${SERVICE_DATABASES}; do
    if ! pg_dump -h postgres -U postgres -Fc -f "${dir}/${svc}.dump" "${svc}"; then
      echo "backup failed: ${svc}"
      ok=0
    fi
  done
  [ "${ok}" = 1 ] && echo "backup done: ${dir}"
  # Локально — 7 последних дней.
  ls -1d /backups/*/ 2>/dev/null | sort -r | tail -n +8 | xargs -r rm -rf
  if command -v aws >/dev/null; then
    ${S3} cp --recursive --quiet "${dir}" "s3://${S3_BUCKET}/backups/postgres/${day}/" && echo "uploaded to s3: ${day}"
    # В хранилище — 30 последних дней.
    ${S3} ls "s3://${S3_BUCKET}/backups/postgres/" | awk '{print $2}' | sort -r | tail -n +31 |
      while read -r old; do ${S3} rm --recursive --quiet "s3://${S3_BUCKET}/backups/postgres/${old}"; done
  fi
}

# Первая копия — через 10 минут после старта, дальше — каждые сутки около 01:00 UTC.
sleep 600
while true; do
  backup
  now=$(date -u +%s)
  next=$(date -u -d "$(date -u +%Y-%m-%d) 01:00" +%s 2>/dev/null || echo $((now + 86400)))
  [ "${next}" -le "${now}" ] && next=$((next + 86400))
  sleep $((next - now))
done
