#!/bin/sh
# Собирает .env боевого окружения из terraform output и новых случайных секретов.
#   cd infra/terraform && sh render-env.sh > ../../.env.prod
# Файл .env.prod затем копируется на сервер как /opt/testmatica/.env (см. docs/deploy.md).
set -eu
terraform output -json | python3 -c '
import json, sys
o = {k: v["value"] for k, v in json.load(sys.stdin).items()}
print("DOMAIN=tmatica.ru")
print("LIVEKIT_DOMAIN=live.tmatica.ru")
print("ACME_EMAIL=info@tmatica.ru")
print("REGISTRY=" + o["registry"])
print("TAG=latest")
print("PG_HOST=" + o["pg_host"])
for svc, pwd in sorted(o["pg_passwords"].items()):
    print(f"PG_PASSWORD_{svc.upper()}={pwd}")
print("S3_ACCESS_KEY=" + o["s3_access_key"])
print("S3_SECRET_KEY=" + o["s3_secret_key"])
print("S3_BUCKET_FILES=tmatica-files")
print("S3_BUCKET_RECORDINGS=tmatica-recordings")
print("SMTP_USERNAME=" + o["smtp_username"])
print("SMTP_PASSWORD=" + o["smtp_password"])
print("PAYMENT_PROVIDER=disabled")
'
sh "$(dirname "$0")/../prod/gen-secrets.sh"
