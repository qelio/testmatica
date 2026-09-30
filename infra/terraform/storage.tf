# Бакеты закрыты: файлы отдаются по временным ссылкам, которые подписывают сервисы media и video.

resource "yandex_storage_bucket" "files" {
  bucket     = var.bucket_files
  access_key = yandex_iam_service_account_static_access_key.storage.access_key
  secret_key = yandex_iam_service_account_static_access_key.storage.secret_key
  depends_on = [yandex_resourcemanager_folder_iam_member.storage_editor]
}

resource "yandex_storage_bucket" "recordings" {
  bucket     = var.bucket_recordings
  access_key = yandex_iam_service_account_static_access_key.storage.access_key
  secret_key = yandex_iam_service_account_static_access_key.storage.secret_key
  depends_on = [yandex_resourcemanager_folder_iam_member.storage_editor]

  # Записи занятий и прокторинга удаляет сервис video (14 или 30 дней). Правило — страховка:
  # старше 35 дней ничего не хранится, как обещано в политике обработки ПД.
  lifecycle_rule {
    id      = "expire-old-recordings"
    enabled = true
    expiration {
      days = 35
    }
  }
}
