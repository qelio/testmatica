# Тестматика — заметки для разработки

Документы: `docs/mvp-plan.md` (этапы), `docs/architecture.md` (сервисы, события, БД), `docs/decisions.md` (решения по ТЗ).
Интерфейс и тексты — на русском. Комментарии в коде — на русском.

## Запуск и проверка

- Всё работает в Docker: `make up`, `make test`, `make test-<svc>`.
- Тесты сервиса: `docker compose run --rm --no-deps <svc> pytest -q` (используют БД `<svc>_test`, брокер не нужен).
- Веб: `docker compose exec -T web sh -c "npx tsc --noEmit && npm run lint"`.
- Коды из писем при ручной проверке — в Mailpit: `http://localhost:8025`.

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
- Схема БД меняется только миграциями: `make migration s=<svc> m="..."`.

## Правила веба

- Next.js 16 — перед использованием API сверяться с `web/node_modules/next/dist/docs/` (см. `web/AGENTS.md`).
- Запросы к API — через `web/src/lib/api.ts`; access-токен только в памяти, refresh — httpOnly-cookie.
- Цвета — только токены из `globals.css` (`bg-surface`, `text-fg-soft`, `bg-brand`…), тёмная тема автоматически.
