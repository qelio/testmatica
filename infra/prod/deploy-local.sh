#!/usr/bin/env bash
# Выкладка с компьютера разработчика (решение №71): GitHub Actions недоступны, код по-прежнему хранится на GitHub.
#   make deploy            — сайт и сервисы, изменившиеся с прошлой выкладки (сайт собирается всегда: в нём номер версии)
#   make deploy all=1      — все образы заново
#   make deploy dry=1      — только показать план, ничего не собирать и не менять
#   make rollback          — вернуть на сервере предыдущую версию
# Выкладывается то, что уже отправлено в main. Образы собираются здесь под архитектуру сервера (linux/amd64)
# и переносятся по SSH, реестр образов не нужен. Миграции БД сервисы применяют сами при старте.
set -euo pipefail
cd "$(dirname "$0")/../.."

TARGET="${DEPLOY_TARGET:-deploy@testmatica.ru}"
KEY="${DEPLOY_KEY:-$HOME/.ssh/testmatica}"
SITE="${DEPLOY_SITE:-https://testmatica.ru}"
R=ghcr.io/qelio/testmatica # имя образов на сервере — как раньше в реестре GitHub, compose.prod.yaml не меняется
PY="identity mcp notification audit classroom schedule academic chat whiteboard media content moderation assessment marketplace billing video"
ALL_SERVICES="$PY code-runner web"
PROD_FILES="compose.prod.yaml infra/prod/deploy.sh infra/prod/postgres-init.sh infra/prod/postgres-backup.sh"

remote() { ssh -i "$KEY" -o BatchMode=yes -o ServerAliveInterval=30 "$TARGET" "$@"; }
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\n\033[31m%s\033[0m\n' "$*" >&2; exit 1; }
has() { case " $1 " in *" $2 "*) return 0 ;; *) return 1 ;; esac; }

if [ "${1:-}" = rollback ]; then
  say "Откат на предыдущую версию"
  remote 'set -e; cd /opt/testmatica
    test -s previous-tag || { echo "Предыдущая версия не записана"; exit 1; }
    PREV=$(cat previous-tag); CUR=$(grep "^TAG=" .env | cut -d= -f2)
    sed -i "s/^TAG=.*/TAG=$PREV/" .env && echo "$CUR" > previous-tag
    docker compose -f compose.prod.yaml up -d --pull never --remove-orphans
    echo "Сейчас на сервере: $PREV (вернуться обратно — ещё раз make rollback)"'
  exit 0
fi

# 1. Выкладываем только то, что уже в main на GitHub.
# В режиме dry=1 нарушения только показываются: план можно посмотреть и до коммита.
check() { if [ -n "${DRY:-}" ]; then echo "  внимание: $1"; else fail "$1"; fi; }
git fetch -q origin main --tags
[ "$(git branch --show-current)" = main ] || check "Выкладка — только из ветки main."
[ -z "$(git status --porcelain)" ] || check "Есть незакоммиченные изменения — сначала коммит."
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || check "Ветка main не совпадает с GitHub — сначала git pull или git push."
SHA=$(git rev-parse HEAD)
VERSION=$(sh infra/prod/next-version.sh | cut -d= -f2)

CUR=$(remote "grep '^TAG=' /opt/testmatica/.env | cut -d= -f2")
[ "$CUR" != "$SHA" ] || { say "Эта версия уже на сервере."; exit 0; }

# 2. Что пересобрать: сервисы, чьи файлы изменились с выкладки, которая сейчас на сервере.
BUILD="web"
FULL_UP=0
MIGRATIONS=""
if [ -n "${ALL:-}" ] || ! git cat-file -e "$CUR^{commit}" 2>/dev/null; then
  BUILD="$ALL_SERVICES"
  FULL_UP=1
else
  for f in $(git diff --name-only "$CUR" "$SHA"); do
    case "$f" in
      libs/* | infra/docker/python-service.Dockerfile) for s in $PY; do has "$BUILD" "$s" || BUILD="$BUILD $s"; done ;;
      services/*)
        s=${f#services/}; s=${s%%/*}
        { has "$PY" "$s" || [ "$s" = code-runner ]; } && ! has "$BUILD" "$s" && BUILD="$BUILD $s"
        case "$f" in */migrations/versions/*) has "$MIGRATIONS" "$s" || MIGRATIONS="$MIGRATIONS $s" ;; esac
        ;;
      compose.prod.yaml | infra/prod/deploy.sh | infra/prod/postgres-*.sh) FULL_UP=1 ;;
    esac
  done
fi
# Несобираемые сервисы получают новый тег от старого образа; если старого нет — собираем и их.
KEEP=""
for s in $ALL_SERVICES; do has "$BUILD" "$s" || KEEP="$KEEP $s"; done
if [ -n "$KEEP" ]; then
  MISSING=$(remote "for s in $KEEP; do docker image inspect $R/\$s:$CUR >/dev/null 2>&1 || echo \$s; done")
  for s in $MISSING; do BUILD="$BUILD $s"; KEEP=$(echo " $KEEP " | sed "s/ $s / /"); done
fi

say "Версия $VERSION: $(git log -1 --format='%h %s')"
echo "Сейчас на сервере: ${CUR:0:7}"
echo "Собрать:$( for s in $BUILD; do printf ' %s' "$s"; done)"
[ -z "$MIGRATIONS" ] || echo "Новые миграции (перед выкладкой — копия баз):$MIGRATIONS"
[ "$FULL_UP" = 0 ] || echo "Перезапуск всех контейнеров: менялись файлы сервера или собираются все образы"
[ -z "${DRY:-}" ] || exit 0

# 3. Сборка под архитектуру сервера.
docker info >/dev/null 2>&1 || {
  say "Запускаю Docker Desktop…"
  open -a Docker 2>/dev/null || true
  for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 3; done
  docker info >/dev/null 2>&1 || fail "Docker не запустился."
}
for s in $BUILD; do
  printf '  сборка %-13s' "$s"
  start=$(date +%s)
  case "$s" in
    web) docker build -q --platform linux/amd64 --provenance=false --build-arg APP_VERSION="$VERSION" -t "$R/web:$SHA" web >/dev/null ;;
    code-runner) docker build -q --platform linux/amd64 --provenance=false -t "$R/code-runner:$SHA" services/code-runner >/dev/null ;;
    *) docker build -q --platform linux/amd64 --provenance=false --build-arg SERVICE="$s" -f infra/docker/python-service.Dockerfile -t "$R/$s:$SHA" . >/dev/null ;;
  esac
  echo "$(($(date +%s) - start)) с"
done

# 4. Перенос образов и файлов на сервер.
say "Перенос на сервер"
IMAGES=""
for s in $BUILD; do IMAGES="$IMAGES $R/$s:$SHA"; done
# shellcheck disable=SC2086
docker save $IMAGES | gzip -1 | remote 'gunzip | docker load' | sed 's/^/  /'
for f in $PROD_FILES; do scp -q -i "$KEY" "$f" "$TARGET:/opt/testmatica/$(basename "$f")"; done

# 5. Переключение. Образы предыдущей версии остаются на сервере — для make rollback.
say "Переключение"
if [ "$FULL_UP" = 1 ]; then UP="--remove-orphans"; else UP="--no-deps$( for s in $BUILD; do printf ' %s' "$s"; done)"; fi
remote "set -e; cd /opt/testmatica; R=$R; SHA=$SHA; CUR=$CUR
  for s in $KEEP; do docker tag \$R/\$s:\$CUR \$R/\$s:\$SHA; done
  for db in $MIGRATIONS; do
    mkdir -p predeploy
    docker compose -f compose.prod.yaml exec -T postgres pg_dump -U postgres -Fc \$db > predeploy/\$db-\$(date +%F-%H%M).dump
    echo \"  копия базы \$db: predeploy/\"
  done
  ls -1t predeploy/*.dump 2>/dev/null | tail -n +21 | xargs -r rm -f
  echo \$CUR > previous-tag
  sed -i \"s/^TAG=.*/TAG=\$SHA/\" .env
  docker compose -f compose.prod.yaml up -d --pull never $UP 2>&1 | grep -v -E 'Running|Waiting|Healthy' || true
  docker images --format '{{.Repository}}:{{.Tag}}' | grep \"^\$R/\" | grep -v -e \":\$SHA\\\$\" -e \":\$CUR\\\$\" | xargs -r docker rmi >/dev/null 2>&1 || true
  docker image prune -f >/dev/null"

# 6. Проверка: контейнеры работают, сайт открывается и показывает новую версию.
say "Проверка"
ok=0
for _ in $(seq 1 30); do
  sleep 4
  bad=$(remote "cd /opt/testmatica; docker compose -f compose.prod.yaml ps -a --format '{{.Service}} {{.State}}' | grep -v ' running\$' | grep -v '^postgres-backup ' || true")
  page=$(curl -fsS --max-time 15 "$SITE/" 2>/dev/null || true)
  if [ -z "$bad" ] && printf '%s' "$page" | grep -q "Версия <!-- -->$VERSION"; then ok=1; break; fi
done
if [ "$ok" != 1 ]; then
  [ -z "${bad:-}" ] || printf 'Не работают контейнеры:\n%s\n' "$bad"
  fail "Сайт не подтвердил версию $VERSION. Логи: ssh $TARGET 'cd /opt/testmatica && docker compose -f compose.prod.yaml logs --tail 50 <сервис>'. Вернуть прежнюю версию: make rollback"
fi
echo "  все контейнеры работают, на сайте «Версия $VERSION»"

# 7. Метка версии.
git tag -a "v$VERSION" -m "Выкладка $VERSION" "$SHA"
git push -q origin "v$VERSION"
say "Готово: версия $VERSION на $SITE"
