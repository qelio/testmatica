variable "location" {
  description = "Где сервер: ru-1 — Санкт-Петербург, там же S3 (в Екатеринбурге и Казани 2026-10-12 закончились серверы)"
  type        = string
  default     = "ru-1"
}

# 2 vCPU / 4 ГБ — как ВМ в Яндексе (меньше 4 ГБ памяти контейнерам не хватает). Дешёвый SSD-50 2026-10-12 был
# разобран — взят Cloud-50 (NVMe). Поднять — сменить здесь и terraform apply.
variable "availability_zone" {
  description = "Зона внутри локации (spb-1 … spb-5); null — выберет Timeweb. Нужна, когда в зоне по умолчанию нет мест"
  type        = string
  default     = "spb-3" # 2026-10-12: просили spb-2, Timeweb поставил в spb-3; в других зонах и на SSD-50 мест не было
}

variable "server_preset" {
  description = "Короткое название тарифа (description_short) — в одной локации у одинаковых ресурсов их несколько"
  type        = string
  default     = "Cloud-50"
}

variable "server_cpu" {
  type    = number
  default = 2
}

variable "server_ram_mb" {
  type    = number
  default = 4096
}

variable "server_disk_mb" {
  type    = number
  default = 51200
}

variable "s3_disk_mb" {
  description = "Объём каждого бакета (файлы, записи); при нехватке тариф поднимается сам"
  type        = number
  default     = 10240
}

variable "ssh_public_key" {
  description = "Публичный SSH-ключ для входа на сервер и выкладки из GitHub Actions"
  type        = string
}

variable "vm_user" {
  type    = string
  default = "deploy"
}
