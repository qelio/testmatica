# Тестматика — заметки для разработки

Документы: `docs/mvp-plan.md` (этапы), `docs/architecture.md` (сервисы, события, БД), `docs/decisions.md` (решения по ТЗ).
Интерфейс и тексты — на русском. Комментарии в коде — на русском.

## Запуск и проверка

- Всё работает в Docker: `make up`, `make test`, `make test-<svc>`.
- Тесты сервиса: `docker compose run --rm --no-deps <svc> pytest -q` (используют БД `<svc>_test`, брокер не нужен).
- Веб: `docker compose exec -T web sh -c "npx tsc --noEmit && npm run lint"`.
- Коды из писем при ручной проверке — в Mailpit: `http://localhost:8025`.
- Прод: `compose.prod.yaml` + `infra/terraform` + `.github/workflows/deploy.yml`, порядок — `docs/deploy.md`.
  Новый сервис или переменная окружения — добавить и туда (и в `infra/prod/env.example`); новая база — в сервис `postgres` в `compose.prod.yaml` (решение №38, порядок — `docs/deploy.md`).

## Изменения и выкладка (решение №30)

- Выкладка — `make deploy` с компьютера разработчика (решение №71). Пушить в `main`, вливать PR и запускать выкладку — только по команде пользователя «Выкладывай».
- Крупное изменение — отдельная ветка (`feature/<кратко>`), пушить её можно; готово — PR в `main` (на PR идут проверки и сборка без выкладки).
- Мелкая правка (текст, цвет, небольшой фикс) — в ветке `main`; коммит — по команде «Коммить», пуш — по команде «Выкладывай».
- По команде «Коммить» создать коммит и сразу отправить рабочую ветку на GitHub. Если правка сделана в `main`, для отправки коммита использовать отдельную ветку. Пуш в `main` — по команде «Выкладывай». Force push и удаление `main` запрещены защитой ветки.
- После выкладки — проверить статус сборки (`gh run list`), контейнеры на сервере и сам сайт.

## Правила бэкенда

- Микросервисы (решение заказчика, не предлагать монолит). Брокер — RabbitMQ.
- У каждого сервиса своя БД; чужие таблицы не читать — только REST или события.
- События и команды — только через `Outbox` из `testmatica_common.messaging`, в той же транзакции, что и изменения.
  События: `EVENTS_EXCHANGE`, тип `<сервис>.<сущность>.<действие>`. Команды: очередь `<сервис>.<назначение>`.
  Секреты (коды) — только в командах: audit читает все события.
- Обработчики сообщений — через `runtime.consumer(...)`; идемпотентность даёт inbox.
- Ошибки API — `ApiError(status, code, message, details)`; формат ответа `{"error": {...}}`.
- Права — `auth.principal` / `auth.require(ROLE_...)` из `testmatica_common.auth`.
- Новый сервис: скопировать структуру `services/classroom`, добавить в `compose.yaml` (правило Traefik с `!PathPrefix(.../internal)`),
  в `SERVICE_DATABASES`, в `SERVICES` в Makefile; `make db-init`, `make migration s=<svc> m=initial`; если нужна реплика имён — `make snapshot`.
- Синхронные вызовы между сервисами — только `/internal/...` через `InternalClient` (заголовок X-Internal-Token); наружу не публикуются.
- Имена пользователей в других сервисах — локальная реплика `people`, заполняется событиями `identity.user.registered|updated|snapshot`.
- Схема БД меняется только миграциями: `make migration s=<svc> m="..."`. Автогенерация не видит изменений CHECK-ограничений —
  их пересоздание (`op.drop_constraint` / `op.create_check_constraint`) дописывать в миграцию вручную.
- Подключение Codex — сервис `mcp` (MCP Streamable HTTP, `/api/mcp`, решение №41): личный ключ педагога (identity `api_keys`)
  обменивается на его access-токен, функции (`services/mcp/app/tools.py`) вызывают публичные API сервисов. Новая возможность
  для Codex — новая функция там же, без прямого доступа к базам. Инструкция для педагога — `docs/Codex-connector.md`.
- Видеосвязь — LiveKit (`livekit`, `egress`), доступ к нему — только через сервис video (пропуска, права, запись).
  Запускать через `make up`: Makefile выставляет `LIVEKIT_NODE_IP` (адрес компьютера в сети), без него не работает запись.
- Код учеников выполняется только в `code-runner` (изолированная сеть `sandbox`, read-only, без привилегий); доступ к нему — только у assessment.

## Правила веба

- Next.js 16 — перед использованием API сверяться с `web/node_modules/next/dist/docs/` (см. `web/AGENTS.md`).
- Запросы к API — через `web/src/lib/api.ts`; access-токен только в памяти, refresh — httpOnly-cookie.
- Цвета — только токены из `globals.css` (`bg-surface`, `text-fg-soft`, `bg-brand`…). Тема — по системе или выбор пользователя (`lib/theme.tsx`, атрибут `data-theme` на `<html>`); свои цвета компонентов (редактор кода) — через `useDarkMode()`.
