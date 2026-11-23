#!/usr/bin/env bash
# Unseals OpenBao after a restart. Three custodians each enter their unseal key (input hidden).
# Usage (from the repository root): ./scripts/openbao/unseal.sh
set -euo pipefail

for i in 1 2 3; do
  read -r -s -p "Unseal key $i/3: " KEY; echo
  docker compose exec -T openbao bao operator unseal -address=http://127.0.0.1:8200 "$KEY" </dev/null >/dev/null
done
docker compose exec -T openbao bao status -address=http://127.0.0.1:8200 | grep -E "^Sealed"
