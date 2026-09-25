# Короткие команды для локальной разработки. Список: make help

SERVICES := identity notification audit classroom schedule academic chat media content moderation assessment
DC := docker compose

.DEFAULT_GOAL := help

help: ## Показать список команд
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36mmake %-14s\033[0m %s\n", $$1, $$2}'

up: ## Собрать и запустить всё окружение
	$(DC) up -d --build
	@echo ""
	@echo "  Приложение:  http://localhost:8080"
	@echo "  Почта:       http://localhost:8025"
	@echo "  RabbitMQ:    http://localhost:15672  (guest / guest)"
	@echo "  Traefik:     http://localhost:8081"

down: ## Остановить всё (данные сохраняются)
	$(DC) down

reset: ## Остановить и УДАЛИТЬ все локальные данные (базы, очереди, файлы)
	$(DC) down -v

ps: ## Состояние контейнеров
	$(DC) ps

logs: ## Логи всех сервисов (или: make logs s=identity)
	$(DC) logs -f --tail=100 $(s)

test: ## Прогнать тесты всех сервисов
	@for svc in $(SERVICES); do \
		echo "\n=== $$svc ==="; \
		$(DC) run --rm --no-deps $$svc pytest -q || exit 1; \
	done
	$(DC) run --rm code-runner pytest -q -p no:cacheprovider
	$(DC) exec -T web sh -c "npx tsc --noEmit && npm run lint"

test-%: ## Тесты одного сервиса: make test-identity
	$(DC) run --rm --no-deps $* pytest -q

migration: ## Новая миграция: make migration s=identity m="add phone"
	$(DC) run --rm --no-deps -e RUN_BACKGROUND=false $(s) alembic revision --autogenerate -m "$(m)"

snapshot: ## Разослать пользователей, группы и привязки сервисам (после добавления нового сервиса)
	@# Сервис отвечает на /health только после подписки на события — иначе рассылка уйдёт «в никуда».
	@for svc in $(SERVICES); do \
		until curl -sf http://localhost:8080/api/$$svc/health >/dev/null; do echo "жду $$svc…"; sleep 2; done; \
	done
	$(DC) exec identity python -m app.cli publish-snapshot
	$(DC) exec classroom python -m app.cli publish-snapshot

admin: ## Создать администратора: make admin email=admin@example.com
	$(DC) exec identity python -m app.cli create-user --email $(email) --name "Администратор" --role admin

db-init: ## Создать базы для новых сервисов (после добавления в SERVICE_DATABASES)
	$(DC) up -d --wait postgres
	$(DC) exec postgres sh /docker-entrypoint-initdb.d/init-databases.sh

.PHONY: help up down reset ps logs test migration snapshot admin db-init
