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
  default     = "tmatica.ru"
}

variable "livekit_subdomain" {
  description = "Поддомен видеосвязи (LiveKit): live → live.tmatica.ru"
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

variable "vm_cores" {
  type    = number
  default = 4
}

variable "vm_memory_gb" {
  type    = number
  default = 8
}

variable "vm_disk_gb" {
  type    = number
  default = 60
}

variable "pg_preset" {
  description = "Класс хостов Managed PostgreSQL (s2.micro — 2 vCPU, 8 ГБ)"
  type        = string
  default     = "s2.micro"
}

variable "pg_disk_gb" {
  type    = number
  default = 20
}

variable "bucket_files" {
  description = "Бакет файлов (имена бакетов уникальны во всём Object Storage)"
  type        = string
  default     = "tmatica-files"
}

variable "bucket_recordings" {
  description = "Бакет записей занятий и прокторинга"
  type        = string
  default     = "tmatica-recordings"
}
