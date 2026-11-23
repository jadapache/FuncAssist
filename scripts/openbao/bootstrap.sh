#!/usr/bin/env bash
# One-time OpenBao bootstrap for FuncAssist (SEC-01).
#
# Required environment variables:
#   SECRET_KEY   master key used to derive the Fernet key and sign session JWTs
#   PBKDF2_SALT  salt for the key derivation
# For an existing installation, export the CURRENT values so encrypted data stays readable.
# For a new installation, generate them:  openssl rand -hex 32  /  openssl rand -hex 16
#
# Usage (from the repository root):
#   docker compose up -d openbao
#   SECRET_KEY=... PBKDF2_SALT=... ./scripts/openbao/bootstrap.sh
#   docker compose up -d
set -euo pipefail

: "${SECRET_KEY:?SECRET_KEY is required}"
: "${PBKDF2_SALT:?PBKDF2_SALT is required}"

APPROLE_DIR="openbao/approle"
bao() { docker compose exec -T -e BAO_ADDR=http://127.0.0.1:8200 ${BAO_TOKEN:+-e BAO_TOKEN="$BAO_TOKEN"} openbao bao "$@"; }

echo ">> Initializing OpenBao (5 unseal key shares, threshold 3)"
INIT_OUT="$(bao operator init -key-shares=5 -key-threshold=3 | tr -d '\r')"
echo "$INIT_OUT" > openbao-init.txt
chmod 600 openbao-init.txt
echo "   Unseal keys and root token written to ./openbao-init.txt."
echo "   Distribute the unseal keys to 5 custodians, store them offline and DELETE this file."

for i in 1 2 3; do
  bao operator unseal "$(awk -v n="Unseal Key $i:" 'index($0, n) == 1 { print $NF }' <<<"$INIT_OUT")" >/dev/null
done
BAO_TOKEN="$(awk '/^Initial Root Token:/ { print $NF }' <<<"$INIT_OUT")"
export BAO_TOKEN

echo ">> Storing application keys in kv-v2 at secret/funcassist"
bao secrets enable -path=secret kv-v2 >/dev/null
bao kv put secret/funcassist secret_key="$SECRET_KEY" pbkdf2_salt="$PBKDF2_SALT" >/dev/null

echo ">> Creating read-only policy and AppRole for the FuncAssist agent"
docker compose exec -T openbao sh -c 'cat > /tmp/funcassist-policy.hcl' < docker/openbao/funcassist-policy.hcl
bao policy write funcassist /tmp/funcassist-policy.hcl >/dev/null
bao auth enable approle >/dev/null
bao write auth/approle/role/funcassist token_policies=funcassist token_ttl=1h token_max_ttl=4h secret_id_ttl=0 >/dev/null

mkdir -p "$APPROLE_DIR"
bao read -field=role_id auth/approle/role/funcassist/role-id > "$APPROLE_DIR/role_id"
bao write -f -field=secret_id auth/approle/role/funcassist/secret-id > "$APPROLE_DIR/secret_id"
# Only the openbao user of the agent container may read the AppRole credentials.
BAO_UID="$(docker compose exec -T openbao id -u openbao | tr -d '\r')"
docker compose run --rm --no-deps --user 0 -v "$PWD/$APPROLE_DIR:/approle" --entrypoint sh openbao-agent \
  -c "chown -R $BAO_UID /approle && chmod 500 /approle && chmod 400 /approle/role_id /approle/secret_id"

echo ">> Revoking the root token"
bao token revoke -self >/dev/null

echo ">> Done. Start the stack with: docker compose up -d"
