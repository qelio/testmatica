#!/bin/sh
# Собирает .env боевого окружения из terraform output и новых случайных секретов.
#   cd infra/terraform && sh render-env.sh > ../../.env.prod
# Файл .env.prod затем копируется на сервер как /opt/testmatica/.env (см. docs/deploy.md).
set -eu
# Terraform — установленный или из Docker (tf.sh).
if command -v terraform >/dev/null 2>&1; then TF="terraform"; else TF="sh $(dirname "$0")/tf.sh"; fi
$TF output -json | python3 -c '
import json, sys
o = {k: v["value"] for k, v in json.load(sys.stdin).items()}
print("DOMAIN=testmatica.ru")
print("LIVEKIT_DOMAIN=live.testmatica.ru")
print("ACME_EMAIL=info@testmatica.ru")
print("REGISTRY=" + o["registry"])
print("TAG=latest")
print("S3_ACCESS_KEY=" + o["s3_access_key"])
print("S3_SECRET_KEY=" + o["s3_secret_key"])
print("S3_BUCKET_FILES=testmatica-files")
print("S3_BUCKET_RECORDINGS=testmatica-recordings")
print("# true — когда домен подтверждён в Postbox (docs/deploy.md, шаг 4)")
print("EMAIL_ENABLED=false")
print("SMTP_USERNAME=" + o["smtp_username"])
print("SMTP_PASSWORD=" + o["smtp_password"])
print("PAYMENT_PROVIDER=disabled")
'
sh "$(dirname "$0")/../prod/gen-secrets.sh"
