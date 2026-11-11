# Выкладка в Яндекс Облако

Схема (решения №28 и №38): одна ВМ с Docker Compose (`compose.prod.yaml`, в том числе PostgreSQL) + Object Storage + Container Registry + Cloud DNS + Postbox (почта). Инфраструктура описана в `infra/terraform`, сборка и выкладка — GitHub Actions (`.github/workflows/deploy.yml`).

```
                 ┌────────────── ВМ testmatica-app (Ubuntu 24.04, Docker) ───────────────┐
 браузер ─443──▶ │ Traefik (HTTPS, Let's Encrypt) ─▶ web, /api/<сервис> ─▶ 14 сервисов   │
 браузер ─UDP──▶ │ LiveKit (7881/tcp, 7882/udp, TURN 3478/udp) ◀─ egress (запись)       │
                 │ PostgreSQL (14 баз), RabbitMQ, Redis, code-runner (изолированная сеть)│
                 └──────────────────────────────┬──────────────────────────────────────┘
                                                │ HTTPS
                          Object Storage (файлы, записи, копии баз)
```

## Размеры на старт

Рассчитано примерно на 10 пользователей (не одновременно), значения — в `infra/terraform/variables.tf`:
- ВМ: 2 vCPU с гарантированной долей 50%, 4 ГБ памяти + 2 ГБ подкачки, диск 30 ГБ SSD. Все контейнеры в боевом режиме занимают около 1,6 ГБ, запись занятия (Chrome) — ещё до 0,5 ГБ;
- PostgreSQL — контейнер на той же ВМ (решение №38: Managed PostgreSQL обходился дороже ВМ), данные — в томе `pg-data`, русская сортировка (ICU `ru-RU`).

Когда станет тесно (медленные страницы, заикается видео или запись) — поднять `vm_core_fraction` до 100, `vm_memory_gb` до 8 и выполнить `terraform apply`: ВМ перезапустится с новыми ресурсами, данные сохранятся.

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
**Выкладка сейчас (решение №71)** — с компьютера разработчика, GitHub Actions заблокированы:

- `make deploy dry=1` — что изменилось с прошлой выкладки и что будет собрано;
- `make deploy` — сборка образов сайта и изменившихся сервисов (linux/amd64, нужен Docker Desktop), перенос по SSH,
  копия баз перед новыми миграциями, переключение, проверка контейнеров и «Версия X.Y» на сайте, метка `vX.Y`;
- `make deploy all=1` — пересобрать все образы; `make rollback` — вернуть предыдущую версию (и обратно — ещё раз).
- Нужны SSH-ключ `~/.ssh/testmatica` (или `DEPLOY_KEY`) и доступ `deploy@testmatica.ru` (или `DEPLOY_TARGET`).

Раньше (пока работали GitHub Actions): Пуш в `main` → GitHub Actions: проверка веба → 16 образов → выкладка. Миграции применяются при старте сервисов. Сертификаты Let's Encrypt выдаются при первом запросе (домен уже должен смотреть на ВМ).

Администратор (пароль спросит):
```bash
ssh deploy@<vm_ip>
cd /opt/testmatica
docker compose -f compose.prod.yaml exec identity python -m app.cli create-user --email admin@testmatica.ru --last-name "<Фамилия>" --first-name "<Имя>" --role admin
```

### 8. Проверка после запуска
- https://testmatica.ru открывается, сертификат валиден, `http://` и `www.` переадресуют на `https://testmatica.ru`;
- регистрация: сразу пускает в кабинет (пока `EMAIL_ENABLED=false`); после включения почты — письмо с кодом приходит (не в спам);
- загрузка файла и фото профиля; видеозанятие из двух браузеров (в том числе с мобильного интернета) и запись;
- `https://testmatica.ru/api/identity/docs` — 404 (Swagger в проде закрыт);
- оплата тарифа отвечает «скоро появится» (`PAYMENT_PROVIDER=disabled`), тариф выдаёт администратор.

## Повседневное
- **Порядок изменений** (решение №30): крупное — ветка `feature/…` → PR в `main` (проверки и сборка без выкладки) → влить PR; мелкое — коммит сразу в `main`. Любой пуш в `main` выкладывает на сайт.
- **Обновление** — пуш в `main`. Тег образов = коммит.
- **Откат** — `ssh deploy@<vm_ip> sh /opt/testmatica/deploy.sh <предыдущий коммит>`.
- **Логи** — `docker compose -f compose.prod.yaml logs -f <сервис>`.
- **Резервные копии баз** — контейнер `postgres-backup` (`infra/prod/postgres-backup.sh`) раз в сутки около 01:00 UTC делает `pg_dump` каждой базы: на диск ВМ (том `pg-backups`, 7 дней) и в Object Storage `s3://testmatica-files/backups/postgres/<дата>/` (30 дней). Восстановить базу:
  ```
  docker compose -f compose.prod.yaml stop <сервис>
  docker compose -f compose.prod.yaml cp <svc>.dump postgres:/tmp/<svc>.dump
  docker compose -f compose.prod.yaml exec postgres sh -c "pg_restore -l /tmp/<svc>.dump | grep -v ' EXTENSION ' > /tmp/l && pg_restore -U postgres -d <svc> --clean --if-exists --no-owner --role=<svc> -L /tmp/l /tmp/<svc>.dump"
  docker compose -f compose.prod.yaml start <сервис>
  ```
  Файлы — в Object Storage.
- **Новая база** (новый сервис) — в `SERVICE_DATABASES` и `PG_PASSWORD_*` сервиса `postgres` в `compose.prod.yaml`, пароль — в `.env` и `gen-secrets.sh`. Скрипт `postgres-init.sh` работает только на пустом томе — на живом сервере базу и пользователя создать вручную (`CREATE ROLE … LOGIN PASSWORD …; CREATE DATABASE … OWNER …;`).
- **Изменить инфраструктуру** — правка `infra/terraform`, `terraform plan`, `terraform apply`.

## Сервер на Timeweb Cloud (с 2026-10-12, решение №45)

Боевой сервер — Timeweb Cloud, Санкт-Петербург, `testmatica-app` (91.186.197.71), пользователь `deploy`, каталог `/opt/testmatica`.
Разделы выше про Yandex Cloud (ВМ, реестр, `YC_CI_KEY_JSON`) — история; хранилище и реестр теперь такие:

- **Инфраструктура** — `infra/timeweb` (сервер, IPv4, SSH-ключ, бакеты). Токен API — в `infra/timeweb/twc.env`
  (`TWC_TOKEN=…`, панель Timeweb → «API и Terraform»), запуск — `sh infra/timeweb/tf.sh plan|apply|output`.
  Ключи S3 — `sh infra/timeweb/tf.sh output -raw s3_access_key` / `s3_secret_key`.
- **`.env` на сервере**: `REGISTRY=ghcr.io/qelio/testmatica`, `S3_ENDPOINT=https://s3.twcstorage.ru`, `S3_REGION=ru-1`,
  ключи S3 Timeweb, остальные секреты — прежние. Копию `.env` хранить в менеджере паролей.
- **GitHub**: секреты `SSH_HOST` (адрес сервера), `SSH_USER`, `SSH_PRIVATE_KEY`; реестр — ghcr.io через `GITHUB_TOKEN`.
- **DNS** пока в Yandex Cloud DNS: записи `testmatica.ru`, `www`, `live` — на адрес сервера. Перенос в reg.ru:
  в зоне reg.ru завести A-записи `@`, `www`, `live` на адрес сервера, затем сменить DNS-серверы домена на `ns1.reg.ru`, `ns2.reg.ru`.

## Заглушка: авария или технические работы

Страница «Сайт временно не работает» — `infra/maintenance/index.html` (без внешних файлов; причина — абзац `id="reason"`).
Она лежит в Object Storage, а не на ВМ, поэтому работает, даже когда ВМ недоступна:

- бакет `testmatica.ru` — статический сайт (любой адрес отдаёт заглушку), бакет `www.testmatica.ru` — перенаправление на `https://testmatica.ru`;
- HTTPS — сертификат Let's Encrypt `testmatica-stub` из Certificate Manager (продлевается сам: записи `_acme-challenge` в DNS не удалять).

Включить и выключить (переключаются записи `testmatica.ru` и `www` в Cloud DNS; TTL 5 минут — до всех доходит за 5–10 минут;
`live.testmatica.ru` не трогается):

```bash
infra/maintenance/switch.sh on    # перед этим поправьте причину в index.html — скрипт загрузит свежую страницу
infra/maintenance/switch.sh off   # домен обратно на ВМ
```

Пока заглушка включена, `terraform apply` вернул бы записи на ВМ — запускайте его после `off`. Впервые заглушку подняли
2026-10-09: ВМ в ru-central1-a не стартовала после инцидента в дата-центре Яндекса (облако отвечало «Resource allocation
is restricted» и в других зонах).

## Известные ограничения первого этапа
- Одна ВМ: при её перезагрузке сайт недоступен пару минут. Дальше — вторая ВМ под LiveKit или Managed Kubernetes.
- LiveKit и запись (egress) на одной ВМ: если запись не подключается к комнате (egress внутри сети Docker, а LiveKit объявляет публичный адрес), перевести `livekit` и `egress` на `network_mode: host` — проверить при первом видеозанятии.
- Код учеников выполняется в контейнере без сети и привилегий на той же ВМ; при росте — отдельная ВМ или gVisor.
- Состояние Terraform — локальный файл; при работе нескольких человек перенести в Object Storage (backend "s3").
