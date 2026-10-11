output "server_ip" {
  description = "Публичный адрес сервера — в DNS (testmatica.ru, www, live) и в секрет SSH_HOST"
  value       = twc_server_ip.public.ip
}

output "server_preset" {
  value = "${data.twc_presets.app.id}: ${var.server_cpu} vCPU / ${var.server_ram_mb / 1024} ГБ / ${var.server_disk_mb / 1024} ГБ в ${var.location}"
}

output "s3_endpoint" {
  value = twc_s3_bucket.files.hostname
}

output "s3_buckets" {
  value = { files = twc_s3_bucket.files.name, recordings = twc_s3_bucket.recordings.name }
}

output "s3_access_key" {
  value     = twc_s3_bucket.files.access_key
  sensitive = true
}

output "s3_secret_key" {
  value     = twc_s3_bucket.files.secret_key
  sensitive = true
}
