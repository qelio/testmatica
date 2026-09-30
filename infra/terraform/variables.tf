variable "cloud_id" {
  description = "ID облака (yc config get cloud-id)"
  type        = string
}

variable "folder_id" {
  description = "ID каталога (yc config get folder-id)"
  type        = string
}

variable "zone" {
  description = "Зона доступности"
  type        = string
  default     = "ru-central1-a"
}

variable "domain" {
  description = "Домен сайта"
  type        = string
  default     = "testmatica.ru"
}

variable "livekit_subdomain" {
  description = "Поддомен видеосвязи (LiveKit): live → live.testmatica.ru"
  type        = string
  default     = "live"
}

variable "manage_dns" {
  description = "Создать DNS-зону в Yandex Cloud DNS (у регистратора нужно указать NS ns1.yandexcloud.net и ns2.yandexcloud.net)"
  type        = bool
  default     = true
}

variable "ssh_public_key" {
  description = "Публичный SSH-ключ для входа на ВМ и выкладки из GitHub Actions"
  type        = string
}

variable "ssh_allowed_cidrs" {
  description = "С каких адресов пускать по SSH (GitHub Actions ходит с разных адресов — по умолчанию отовсюду, вход только по ключу)"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "vm_user" {
  description = "Пользователь на ВМ"
  type        = string
  default     = "deploy"
}

# Размеры — на старт (около 10 пользователей, не одновременно). Когда станет тесно — поднять здесь
# и выполнить terraform apply: ВМ перезапустится с новыми ресурсами, данные сохранятся.

variable "vm_cores" {
  type    = number
  default = 2
}

variable "vm_core_fraction" {
  description = "Гарантированная доля vCPU, %: 50 — дешевле, для небольшой нагрузки; 100 — постоянная полная мощность"
  type        = number
  default     = 50
}

variable "vm_memory_gb" {
  type    = number
  default = 4
}

variable "vm_disk_gb" {
  type    = number
  default = 30
}

variable "pg_preset" {
  description = "Класс хостов Managed PostgreSQL: b2.medium — 2 vCPU (50%), 4 ГБ, самый маленький из доступных (b2.micro снят с продажи); дальше s3-c2-m8 (100%, 8 ГБ). Список: yc managed-postgresql resource-preset list"
  type        = string
  default     = "b2.medium"
}

variable "pg_disk_gb" {
  type    = number
  default = 10
}

variable "bucket_files" {
  description = "Бакет файлов (имена бакетов уникальны во всём Object Storage)"
  type        = string
  default     = "testmatica-files"
}

variable "bucket_recordings" {
  description = "Бакет записей занятий и прокторинга"
  type        = string
  default     = "testmatica-recordings"
}
