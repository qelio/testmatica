# Managed PostgreSQL: у каждого сервиса своя база и свой пользователь (как локально, infra/postgres/init-databases.sh).

locals {
  services = [
    "identity", "notification", "audit", "classroom", "schedule", "academic", "chat",
    "media", "content", "moderation", "assessment", "marketplace", "billing", "video",
  ]
  # Расширения, которые нужны миграциям (сервис не может включить их сам).
  pg_extensions = {
    schedule = ["btree_gist"]
  }
}

resource "yandex_mdb_postgresql_cluster" "main" {
  name               = "testmatica"
  environment        = "PRODUCTION"
  network_id         = yandex_vpc_network.main.id
  security_group_ids = [yandex_vpc_security_group.pg.id]

  config {
    version = "17"
    resources {
      resource_preset_id = var.pg_preset
      disk_type_id       = "network-ssd"
      disk_size          = var.pg_disk_gb
    }
    backup_retain_period_days = 14
    backup_window_start {
      hours   = 1
      minutes = 0
    }
    pooler_config {
      pooling_mode = "SESSION"
    }
  }

  host {
    zone      = var.zone
    subnet_id = yandex_vpc_subnet.main.id
  }

  maintenance_window {
    type = "WEEKLY"
    day  = "SUN"
    hour = 4
  }
}

resource "random_password" "pg" {
  for_each = toset(local.services)
  length   = 32
  special  = false
}

resource "yandex_mdb_postgresql_user" "svc" {
  for_each   = toset(local.services)
  cluster_id = yandex_mdb_postgresql_cluster.main.id
  name       = each.key
  password   = random_password.pg[each.key].result
  conn_limit = 40
}

resource "yandex_mdb_postgresql_database" "svc" {
  for_each   = toset(local.services)
  cluster_id = yandex_mdb_postgresql_cluster.main.id
  name       = each.key
  owner      = yandex_mdb_postgresql_user.svc[each.key].name
  lc_collate = "ru_RU.UTF-8"
  lc_type    = "ru_RU.UTF-8"

  dynamic "extension" {
    for_each = lookup(local.pg_extensions, each.key, [])
    content {
      name = extension.value
    }
  }
}
