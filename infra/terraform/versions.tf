terraform {
  required_version = ">= 1.6"
  required_providers {
    yandex = {
      source  = "yandex-cloud/yandex"
      version = ">= 0.130"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.6"
    }
  }
}

# Авторизация — переменная окружения YC_TOKEN: export YC_TOKEN=$(yc iam create-token)
provider "yandex" {
  cloud_id  = var.cloud_id
  folder_id = var.folder_id
  zone      = var.zone
}
