#!/bin/sh
# Заглушка «сайт временно не работает» (docs/deploy.md → «Заглушка»).
#
#   infra/maintenance/switch.sh on   — домен на статическую страницу в Object Storage (бакеты testmatica.ru и
#                                      www.testmatica.ru, HTTPS — сертификат testmatica-stub из Certificate Manager);
#                                      перед этим загружает свежую infra/maintenance/index.html
#   infra/maintenance/switch.sh off  — домен обратно на сервер (адрес — из infra/timeweb)
#
# Записи живут 5 минут (TTL 300) — переключение доходит до всех примерно за 5–10 минут.
# live.testmatica.ru (видеосвязь) не трогается. Нужен yc с доступом к каталогу testmatica.
set -eu

ZONE=testmatica
DOMAIN=testmatica.ru
STUB_HOST=$DOMAIN.website.yandexcloud.net.
WWW_HOST=www.$DOMAIN.website.yandexcloud.net.
HERE=$(cd "$(dirname "$0")" && pwd)

# Адрес боевого сервера — из Terraform для Timeweb (решение №45; токен — infra/timeweb/twc.env).
vm_ip() {
  ip=$(sh "$HERE/../timeweb/tf.sh" output -raw server_ip 2>/dev/null) || true
  case "$ip" in
    *.*.*.*) echo "$ip" ;;
    *) echo "Не удалось узнать адрес сервера: sh infra/timeweb/tf.sh output server_ip" >&2; exit 1 ;;
  esac
}

case "${1:-}" in
  on)
    ip=$(vm_ip)
    yc storage s3 cp "$HERE/index.html" "s3://$DOMAIN/index.html" --content-type "text/html; charset=utf-8"
    yc dns zone delete-records --name $ZONE --record "$DOMAIN. 300 A $ip" --record "www.$DOMAIN. 300 A $ip" || true
    yc dns zone add-records --name $ZONE --record "$DOMAIN. 300 ANAME $STUB_HOST" --record "www.$DOMAIN. 300 CNAME $WWW_HOST"
    echo "Заглушка включена: https://$DOMAIN — до всех дойдёт за 5–10 минут."
    ;;
  off)
    ip=$(vm_ip)
    yc dns zone delete-records --name $ZONE --record "$DOMAIN. 300 ANAME $STUB_HOST" --record "www.$DOMAIN. 300 CNAME $WWW_HOST" || true
    yc dns zone add-records --name $ZONE --record "$DOMAIN. 300 A $ip" --record "www.$DOMAIN. 300 A $ip"
    echo "Сайт снова на ВМ ($ip) — до всех дойдёт за 5–10 минут."
    ;;
  *)
    echo "Использование: $0 on|off" >&2
    exit 2
    ;;
esac
