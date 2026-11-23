#!/bin/sh
# Runs from the nginx image entrypoint before nginx starts (/docker-entrypoint.d/).
# FuncAssist is served only over HTTPS (SEC-06): a certificate in /etc/nginx/certs is mandatory.
set -eu

CERT_DIR=/etc/nginx/certs
CONF_DIR=/etc/nginx/funcassist
TARGET=/etc/nginx/conf.d/default.conf

if [ ! -s "$CERT_DIR/tls.crt" ] || [ ! -s "$CERT_DIR/tls.key" ]; then
  echo "funcassist: ERROR no hay certificado en $CERT_DIR (tls.crt + tls.key). FuncAssist solo se sirve por HTTPS." >&2
  exit 1
fi

# Port the browser uses for HTTPS (published port), so redirects point at it.
port="${APP_HTTPS_PORT:-443}"
if [ "$port" = "443" ]; then suffix=""; else suffix=":$port"; fi
sed "s|__HTTPS_PORT_SUFFIX__|$suffix|g" "$CONF_DIR/https.conf" > "$TARGET"
echo "funcassist: HTTPS habilitado con $CERT_DIR/tls.crt (puerto publicado $port)"
