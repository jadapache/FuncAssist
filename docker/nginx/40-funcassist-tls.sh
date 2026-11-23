#!/bin/sh
# Runs from the nginx image entrypoint before nginx starts (/docker-entrypoint.d/).
# Chooses HTTPS when a certificate is mounted in /etc/nginx/certs, plain HTTP otherwise.
set -eu

CERT_DIR=/etc/nginx/certs
CONF_DIR=/etc/nginx/funcassist
TARGET=/etc/nginx/conf.d/default.conf

if [ -s "$CERT_DIR/tls.crt" ] && [ -s "$CERT_DIR/tls.key" ]; then
  # Port the browser uses for HTTPS (published port), so the HTTP redirect points at it.
  port="${APP_HTTPS_PORT:-443}"
  if [ "$port" = "443" ]; then suffix=""; else suffix=":$port"; fi
  sed "s|__HTTPS_PORT_SUFFIX__|$suffix|g" "$CONF_DIR/https.conf" > "$TARGET"
  echo "funcassist: HTTPS habilitado con $CERT_DIR/tls.crt (puerto publicado $port)"
else
  cp "$CONF_DIR/http.conf" "$TARGET"
  echo "funcassist: sin certificado en $CERT_DIR; se sirve solo HTTP (los modelos en el navegador necesitan HTTPS)"
fi
