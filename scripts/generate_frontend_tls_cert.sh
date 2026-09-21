#!/usr/bin/env bash
# Generate a self-signed TLS cert for the ForensicAuth frontend (option B).
# Usage:
#   ./scripts/generate_frontend_tls_cert.sh labfaces02 10.61.229.231
#   FORENSICAUTH_SSL_DIR=/path/to/ssl ./scripts/generate_frontend_tls_cert.sh myhost
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${FORENSICAUTH_SSL_DIR:-$ROOT/deploy/ssl}"
DAYS="${FORENSICAUTH_TLS_DAYS:-825}"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <hostname-or-ip> [extra-hostname-or-ip ...]" >&2
  echo "Example: $0 labfaces02 10.61.229.231" >&2
  exit 1
fi

PRIMARY="$1"
shift

SAN_PARTS=()
add_san() {
  local value="$1"
  if [[ "$value" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    SAN_PARTS+=("IP:${value}")
  else
    SAN_PARTS+=("DNS:${value}")
  fi
}

add_san "$PRIMARY"
for extra in "$@"; do
  add_san "$extra"
done
# Always include localhost for on-box curl checks
add_san "localhost"
add_san "127.0.0.1"

SAN_CSV=$(IFS=,; echo "${SAN_PARTS[*]}")

mkdir -p "$OUT_DIR"
CRT="$OUT_DIR/tls.crt"
KEY="$OUT_DIR/tls.key"

if [[ -f "$CRT" || -f "$KEY" ]]; then
  echo "Refusing to overwrite existing certs in $OUT_DIR" >&2
  echo "Remove tls.crt / tls.key first if you intend to regenerate." >&2
  exit 1
fi

openssl req -x509 -nodes -newkey rsa:2048 -days "$DAYS" \
  -keyout "$KEY" \
  -out "$CRT" \
  -subj "/CN=${PRIMARY}" \
  -addext "subjectAltName=${SAN_CSV}"

chmod 644 "$CRT"
chmod 600 "$KEY"

echo "Wrote:"
echo "  $CRT"
echo "  $KEY"
echo "SAN: $SAN_CSV"
echo
echo "Next:"
echo "  1. Set CORS_ORIGINS=[\"https://${PRIMARY}\"] in .env.production (add other https:// SANs if needed)"
echo "  2. Rebuild/restart frontend: docker compose -f docker-compose.prod.yml ... up -d --build frontend"
echo "  3. Open https://${PRIMARY}/ (accept or install the cert on clients)"
