# Сервисные аккаунты — у каждого только нужные права.

# ВМ: скачивает образы из реестра по своему токену (без паролей на сервере).
resource "yandex_iam_service_account" "vm" {
  name = "testmatica-vm"
}

resource "yandex_resourcemanager_folder_iam_member" "vm_puller" {
  folder_id = var.folder_id
  role      = "container-registry.images.puller"
  member    = "serviceAccount:${yandex_iam_service_account.vm.id}"
}

# Сервисы media и video, запись занятий (egress): бакеты Object Storage.
resource "yandex_iam_service_account" "storage" {
  name = "testmatica-storage"
}

resource "yandex_resourcemanager_folder_iam_member" "storage_editor" {
  folder_id = var.folder_id
  role      = "storage.editor"
  member    = "serviceAccount:${yandex_iam_service_account.storage.id}"
}

resource "yandex_iam_service_account_static_access_key" "storage" {
  service_account_id = yandex_iam_service_account.storage.id
  description        = "S3-ключ сервисов media, video и egress"
}

# GitHub Actions: публикует образы в реестр.
resource "yandex_iam_service_account" "ci" {
  name = "testmatica-ci"
}

resource "yandex_resourcemanager_folder_iam_member" "ci_pusher" {
  folder_id = var.folder_id
  role      = "container-registry.images.pusher"
  member    = "serviceAccount:${yandex_iam_service_account.ci.id}"
}

resource "yandex_iam_service_account_key" "ci" {
  service_account_id = yandex_iam_service_account.ci.id
  description        = "Ключ GitHub Actions для входа в реестр"
}

# Почта: отправка писем через Yandex Cloud Postbox по SMTP (логин — id API-ключа, пароль — его секрет).
resource "yandex_iam_service_account" "mail" {
  name = "testmatica-mail"
}

resource "yandex_resourcemanager_folder_iam_member" "mail_sender" {
  folder_id = var.folder_id
  role      = "postbox.sender"
  member    = "serviceAccount:${yandex_iam_service_account.mail.id}"
}

resource "yandex_iam_service_account_api_key" "mail" {
  service_account_id = yandex_iam_service_account.mail.id
  description        = "SMTP-пароль сервиса notification (Postbox)"
  scopes             = ["yc.postbox.send"]
}
