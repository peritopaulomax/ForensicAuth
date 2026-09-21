#!/bin/sh
# Ensure TLS material exists, then start nginx.
# Production: mount host certs at /etc/nginx/ssl/{tls.crt,tls.key}.
# Without a mount, generate an ephemeral self-signed cert (local/dev convenience).
set -e

CERT="/etc/nginx/ssl/tls.crt"
KEY="/etc/nginx/ssl/tls.key"
mkdir -p /etc/nginx/ssl

if [ ! -f "$CERT" ] || [ ! -f "$KEY" ]; then
  echo "forensicauth-frontend: no TLS cert mounted; generating ephemeral self-signed cert"
  CN="${TLS_CN:-localhost}"
  # SAN: localhost + optional TLS_EXTRA_SAN (comma-separated DNS: or IP: entries)
  SAN="DNS:localhost,IP:127.0.0.1"
  if [ -n "${TLS_EXTRA_SAN:-}" ]; then
    SAN="${SAN},${TLS_EXTRA_SAN}"
  fi
  openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout "$KEY" \
    -out "$CERT" \
    -subj "/CN=${CN}" \
    -addext "subjectAltName=${SAN}"
  chmod 644 "$CERT"
  chmod 600 "$KEY"
fi

exec nginx -g "daemon off;"
