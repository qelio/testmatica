# Переезд с Yandex Cloud (решение №45): один сервер с Docker Compose, как раньше, и два бакета S3.
# DNS пока остаётся в Yandex Cloud DNS (infra/terraform) — домен переключается записями A.

data "twc_os" "ubuntu" {
  name    = "ubuntu"
  version = "24.04"
}

data "twc_presets" "app" {
  location          = var.location
  cpu               = var.server_cpu
  ram               = var.server_ram_mb
  disk              = var.server_disk_mb
  description_short = var.server_preset
}

resource "twc_ssh_key" "deploy" {
  name = "testmatica-deploy"
  body = var.ssh_public_key
}

resource "twc_server" "app" {
  name         = "testmatica-app"
  hostname     = "testmatica-app"
  os_id        = data.twc_os.ubuntu.id
  preset_id    = data.twc_presets.app.id
  # Задаётся только при создании — «No free node» лечится выбором другой зоны.
  availability_zone = var.availability_zone
  ssh_keys_ids = [twc_ssh_key.deploy.id]
  # Первичная настройка — та же, что была в Яндексе: пользователь deploy, Docker, подкачка.
  cloud_init = templatefile("${path.module}/../terraform/cloud-init.yaml", {
    user    = var.vm_user
    ssh_key = var.ssh_public_key
  })

  lifecycle {
    ignore_changes = [cloud_init, os_id, availability_zone]
  }
}

# Публичный IPv4 у Timeweb — отдельная услуга (в тариф не входит): без него сайт снаружи не открыть.
resource "twc_server_ip" "public" {
  source_server_id = twc_server.app.id
  type             = "ipv4"
  ptr              = "testmatica.ru"
}

# ---------- межсетевой экран ----------
# Экрана Timeweb нет: он не запоминает соединения (ответы на исходящие запросы — DNS, apt, Docker-образы, S3 —
# режутся политикой DROP). Снаружи и так доступны только порты, которые публикует compose.prod.yaml
# (80, 443 — Traefik; 7881/tcp, 7882/udp, 3478/udp, 30000–30100/udp — LiveKit), и SSH по ключу.

# ---------- хранилище: файлы (вложения, картинки, резервные копии базы) и записи занятий ----------

data "twc_s3_preset" "standard" {
  location          = "ru-1"
  disk              = var.s3_disk_mb
  # Стандартный класс: той же ёмкости, что премиальный, но дешевле (79 ₽ против 99 ₽ за 10 ГБ).
  description_short = "Standard ${var.s3_disk_mb / 1024}GB"
}

resource "twc_s3_bucket" "files" {
  name                  = "testmatica-files"
  type                  = "private"
  preset_id             = data.twc_s3_preset.standard.id
  is_allow_auto_upgrade = true
}

resource "twc_s3_bucket" "recordings" {
  name                  = "testmatica-recordings"
  type                  = "private"
  preset_id             = data.twc_s3_preset.standard.id
  is_allow_auto_upgrade = true
}
