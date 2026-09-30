#!/bin/sh
# Terraform из официального Docker-образа (ставить не нужно; провайдеры — с зеркала Яндекса).
#   export YC_TOKEN=$(yc iam create-token)   # токен на 12 часов
#   sh tf.sh init | plan | apply | output ...
set -eu
cd "$(dirname "$0")"
: "${YC_TOKEN:?сначала: export YC_TOKEN=\$(yc iam create-token)}"
# -it — только в терминале (apply спрашивает подтверждение).
TTY=""; [ -t 0 ] && TTY="-it"
exec docker run --rm $TTY \
  -e YC_TOKEN \
  -v "$PWD:/tf" -w /tf \
  -v "$PWD/terraformrc:/root/.terraformrc:ro" \
  hashicorp/terraform:1.9 "$@"
