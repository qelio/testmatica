output "vm_ip" {
  description = "Публичный адрес ВМ (DNS-записи, SSH, GitHub Actions)"
  value       = yandex_vpc_address.app.external_ipv4_address[0].address
}

output "registry" {
  description = "REGISTRY для .env и переменной GitHub"
  value       = "cr.yandex/${yandex_container_registry.main.id}"
}

output "s3_access_key" {
  value     = yandex_iam_service_account_static_access_key.storage.access_key
  sensitive = true
}

output "s3_secret_key" {
  value     = yandex_iam_service_account_static_access_key.storage.secret_key
  sensitive = true
}

output "smtp_username" {
  value = yandex_iam_service_account_api_key.mail.id
}

output "smtp_password" {
  value     = yandex_iam_service_account_api_key.mail.secret_key
  sensitive = true
}

# Авторизованный ключ для docker login в GitHub Actions (секрет YC_CI_KEY_JSON).
output "ci_key_json" {
  value = jsonencode({
    id                 = yandex_iam_service_account_key.ci.id
    service_account_id = yandex_iam_service_account.ci.id
    created_at         = yandex_iam_service_account_key.ci.created_at
    key_algorithm      = yandex_iam_service_account_key.ci.key_algorithm
    public_key         = yandex_iam_service_account_key.ci.public_key
    private_key        = yandex_iam_service_account_key.ci.private_key
  })
  sensitive = true
}

output "dns_name_servers" {
  description = "Указать у регистратора домена"
  value       = var.manage_dns ? ["ns1.yandexcloud.net", "ns2.yandexcloud.net"] : []
}
