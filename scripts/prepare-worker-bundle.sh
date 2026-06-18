#!/usr/bin/env bash
# Empacota backend + deps para worker GPU remoto (rsync).
# Uso: ./scripts/prepare-worker-bundle.sh [user@host:/path/VA\ Suite]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-}"

if [[ -z "$DEST" ]]; then
  echo "Uso: $0 user@host:/caminho/VA\\ Suite"
  echo "Exemplo: $0 perito@10.61.242.100:/home/perito/VA\\ Suite"
  exit 1
fi

echo "==> Sincronizando bundle para $DEST"

rsync -avz --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '.dev-pids' \
  --exclude '.dev-logs' \
  --exclude 'uploads-dev' \
  --exclude 'results-dev' \
  --exclude 'derivatives-dev' \
  --exclude 'peritus_cases-dev' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude 'src/frontend/dist' \
  "$ROOT/requirements.txt" \
  "$ROOT/requirements-gpu.txt" \
  "$ROOT/src/backend/" \
  "$ROOT/scripts/nfs-exports.example" \
  "$ROOT/docs/deploy/WORKER-REMOTE.md" \
  "$DEST/"

echo "Bundle enviado. No worker:"
echo "  conda create -y -n va-suite python=3.11 && conda activate va-suite"
echo "  pip install -r requirements.txt -r requirements-gpu.txt"
echo "  cp src/backend/.env.worker-gpu.example src/backend/.env"
echo "  # Ajuste DATABASE_URL/REDIS_URL para IP da maquina principal"
echo "  cd src/backend && celery -A app.celery_app worker -Q gpu -c 1 -n gpu-maquina2@%h"
