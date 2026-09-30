# Выкладка в Яндекс Облако

Схема (решение №28): одна ВМ с Docker Compose (`compose.prod.yaml`) + Managed PostgreSQL + Object Storage + Container Registry + Cloud DNS + Postbox (почта). Инфраструктура описана в `infra/terraform`, сборка и выкладка — GitHub Actions (`.github/workflows/deploy.yml`).

```
                 ┌────────────── ВМ testmatica-app (Ubuntu 24.04, Docker) ───────────────┐
 браузер ─443──▶ │ Traefik (HTTPS, Let's Encrypt) ─▶ web, /api/<сервис> ─▶ 14 сервисов   │
 браузер ─UDP──▶ │ LiveKit (7881/tcp, 7882/udp, TURN 3478/udp) ◀─ egress (запись)       │
                 │ RabbitMQ, Redis, code-runner (изолированная сеть)                     │
                 └───────┬────────────────────────────┬─────────────────────────────────┘
                         │ 6432 (SSL)                 │ HTTPS
              Managed PostgreSQL              Object Storage (файлы, записи)
```

## Размеры на старт

Рассчитано примерно на 10 пользователей (не одновременно), значения — в `infra/terraform/variables.tf`:
- ВМ: 2 vCPU с гарантированной долей 50%, 4 ГБ памяти + 2 ГБ подкачки, диск 30 ГБ SSD. Все контейнеры в боевом режиме занимают около 1,6 ГБ, запись занятия (Chrome) — ещё до 0,5 ГБ;
- Managed PostgreSQL: `b2.micro` (2 vCPU с долей 20%, 2 ГБ), диск 10 ГБ SSD.

Когда станет тесно (медленные страницы, заикается видео или запись) — поднять `vm_core_fraction` до 100, `vm_memory_gb` до 8, `pg_preset` до `b2.medium` и выполнить `terraform apply`: ВМ и база перезапустятся с новыми ресурсами, данные сохранятся.

## Что нужно один раз

### 1. Облако и инструменты (владелец)
1. Аккаунт в [console.yandex.cloud](https://console.yandex.cloud), платёжный аккаунт, каталог (например, `testmatica`).
2. Установить `yc` ([инструкция](https://yandex.cloud/ru/docs/cli/quickstart)) и выполнить `yc init`.
3. Установить Terraform. Если реестр HashiCorp недоступен — зеркало Яндекса в `~/.terraformrc`:
   ```
   provider_installation {
     network_mirror { url = "https://terraform-mirror.yandexcloud.net/" include = ["registry.terraform.io/*/*"] }
     direct { exclude = ["registry.terraform.io/*/*"] }
   }
   ```
4. SSH-ключ для сервера и выкладки: `ssh-keygen -t ed25519 -f ~/.ssh/testmatica -C deploy@testmatica`.

### 2. Инфраструктура
```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # cloud_id, folder_id — из yc config list; ssh_public_key — ~/.ssh/testmatica.pub
export YC_TOKEN=$(yc iam create-token)
terraform init
terraform plan      # проверить, что будет создано
terraform apply
```
Файл состояния `terraform.tfstate` содержит пароли — хранить только у себя (в git он не попадает).

### 3. Домен
У регистратора testmatica.ru указать NS-серверы: `ns1.yandexcloud.net`, `ns2.yandexcloud.net`. Записи `testmatica.ru`, `www` и `live` Terraform уже создал. Проверка: `dig +short testmatica.ru` показывает `terraform output vm_ip`.

### 4. Почта (Postbox) — можно позже
Пока почты нет, в `.env` стоит `EMAIL_ENABLED=false` (решение №29): регистрация без подтверждения email, вход без кода, сброс пароля и смена email — «скоро» (временный пароль выдаёт администратор). Когда домен подтверждён — `EMAIL_ENABLED=true` и `docker compose -f compose.prod.yaml up -d`.

1. В консоли: Postbox → «Создать адрес» → домен `testmatica.ru`.
2. Добавить в Cloud DNS записи, которые покажет Postbox (DKIM — TXT), и SPF/DMARC по его подсказкам.
3. Дождаться статуса «Подтверждён». Письма уходят с `no-reply@testmatica.ru`.

### 5. Переменные окружения сервера
```bash
cd infra/terraform
sh render-env.sh > ../../.env.prod          # значения из Terraform + новые случайные секреты
scp ../../.env.prod deploy@$(terraform output -raw vm_ip):/opt/testmatica/.env
ssh deploy@$(terraform output -raw vm_ip) chmod 600 /opt/testmatica/.env
```
`.env.prod` после копирования удалить или хранить в менеджере паролей: без него не восстановить секреты.

### 6. GitHub
1. Приватный репозиторий, `git push`.
2. Settings → Secrets and variables → Actions:
   - секреты: `YC_CI_KEY_JSON` (`terraform output -raw ci_key_json`), `SSH_PRIVATE_KEY` (содержимое `~/.ssh/testmatica`), `SSH_HOST` (`terraform output -raw vm_ip`), `SSH_USER` (`deploy`);
   - переменная: `REGISTRY` (`terraform output -raw registry`).
3. Settings → Environments → `production` (можно включить ручное подтверждение выкладки).

### 7. Первый запуск
Пуш в `main` → GitHub Actions: проверка веба → 16 образов → выкладка. Миграции применяются при старте сервисов. Сертификаты Let's Encrypt выдаются при первом запросе (домен уже должен смотреть на ВМ).

Администратор (пароль спросит):
```bash
ssh deploy@<vm_ip>
cd /opt/testmatica
docker compose -f compose.prod.yaml exec identity python -m app.cli create-user --email admin@testmatica.ru --name "Администратор" --role admin
```

### 8. Проверка после запуска
- https://testmatica.ru открывается, сертификат валиден, `http://` и `www.` переадресуют на `https://testmatica.ru`;
- регистрация: сразу пускает в кабинет (пока `EMAIL_ENABLED=false`); после включения почты — письмо с кодом приходит (не в спам);
- загрузка файла и фото профиля; видеозанятие из двух браузеров (в том числе с мобильного интернета) и запись;
- `https://testmatica.ru/api/identity/docs` — 404 (Swagger в проде закрыт);
- оплата тарифа отвечает «скоро появится» (`PAYMENT_PROVIDER=disabled`), тариф выдаёт администратор.

## Повседневное
- **Обновление** — пуш в `main`. Тег образов = коммит.
- **Откат** — `ssh deploy@<vm_ip> sh /opt/testmatica/deploy.sh <предыдущий коммит>`.
- **Логи** — `docker compose -f compose.prod.yaml logs -f <сервис>`.
- **Резервные копии** — Managed PostgreSQL сам хранит 14 дней (восстановление на момент времени в консоли). Файлы — в Object Storage.
- **Изменить инфраструктуру** — правка `infra/terraform`, `terraform plan`, `terraform apply`.

## Известные ограничения первого этапа
- Одна ВМ: при её перезагрузке сайт недоступен пару минут. Дальше — вторая ВМ под LiveKit или Managed Kubernetes.
- LiveKit и запись (egress) на одной ВМ: если запись не подключается к комнате (egress внутри сети Docker, а LiveKit объявляет публичный адрес), перевести `livekit` и `egress` на `network_mode: host` — проверить при первом видеозанятии.
- Код учеников выполняется в контейнере без сети и привилегий на той же ВМ; при росте — отдельная ВМ или gVisor.
- Состояние Terraform — локальный файл; при работе нескольких человек перенести в Object Storage (backend "s3").
