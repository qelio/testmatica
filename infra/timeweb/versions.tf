terraform {
  required_version = ">= 1.6"
  required_providers {
    twc = {
      source  = "timeweb-cloud/timeweb-cloud"
      version = ">= 1.6"
    }
  }
}

# Авторизация — переменная окружения TWC_TOKEN (infra/timeweb/twc.env, не в git); запуск — sh tf.sh …
provider "twc" {}
