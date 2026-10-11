#!/bin/sh
# Terraform для Timeweb Cloud из официального Docker-образа (провайдеры — с зеркала Яндекса, как в infra/terraform).
#   токен — в infra/timeweb/twc.env (TWC_TOKEN=…, файл не в git)
#   sh infra/timeweb/tf.sh init | plan | apply | output …
set -eu
cd "$(dirname "$0")"
[ -f twc.env ] || { echo "нет infra/timeweb/twc.env с TWC_TOKEN" >&2; exit 1; }
TTY=""; [ -t 0 ] && TTY="-it"
exec docker run --rm $TTY \
  --env-file twc.env \
  -e TF_VAR_ssh_public_key="$(cat "${SSH_PUBLIC_KEY_FILE:-$HOME/.ssh/testmatica.pub}")" \
  -v "$PWD/..:/infra" -w /infra/timeweb \
  -v "$PWD/terraformrc:/root/.terraformrc:ro" \
  hashicorp/terraform:1.9 "$@"
