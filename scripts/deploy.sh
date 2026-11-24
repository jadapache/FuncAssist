#!/usr/bin/env bash
# Production deployment entrypoint. Safe to run repeatedly.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

for required in .env certs/tls.crt certs/tls.key openbao/approle/role_id openbao/approle/secret_id; do
  [[ -e "$required" ]] || { echo "ERROR: falta $required" >&2; exit 1; }
done

docker compose config --quiet
docker compose up -d openbao db valkey

if ! docker compose exec -T openbao bao status -address=http://127.0.0.1:8200 >/dev/null 2>&1; then
  echo "ERROR: OpenBao no esta inicializado o desellado. Ejecute scripts/openbao/unseal.sh." >&2
  exit 1
fi

docker compose up -d openbao-agent
for attempt in {1..30}; do
  if docker compose exec -T openbao-agent sh -c 'test -s /run/secrets/funcassist/secret_key && test -s /run/secrets/funcassist/pbkdf2_salt && test -s /run/secrets/funcassist/postgres_password'; then
    break
  fi
  [[ "$attempt" -eq 30 ]] && { echo "ERROR: OpenBao Agent no renderizo los secretos." >&2; exit 1; }
  sleep 2
done

docker compose up -d backend frontend
docker compose ps
