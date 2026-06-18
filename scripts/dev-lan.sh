#!/usr/bin/env bash
# Inicia ForensicAuth em modo desenvolvimento com acesso na LAN.
# Uso: ./scripts/dev-lan.sh start | stop | status
set -euo pipefail

# Evita que proxy corporativo (Squid) intercepte localhost durante dev
export NO_PROXY="localhost,127.0.0.1,10.0.0.0/8,192.168.0.0/16"
export no_proxy="$NO_PROXY"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY 2>/dev/null || true

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/src/backend"
FRONTEND="$ROOT/src/frontend"
PID_DIR="$ROOT/.dev-pids"
LOG_DIR="$ROOT/.dev-logs"
CONDA_ENV="${FORENSIC_AUTH_CONDA_ENV:-forensicauth}"

mkdir -p "$PID_DIR" "$LOG_DIR"
mkdir -p "$ROOT/uploads-dev" "$ROOT/results-dev" "$ROOT/derivatives-dev" \
         "$ROOT/peritus_cases-dev" "$ROOT/models-dev"

_conda() {
  # shellcheck disable=SC1091
  source "$(conda info --base)/etc/profile.d/conda.sh"
  conda activate "$CONDA_ENV"
}

_server_ip() {
  hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1"
}

cmd_start() {
  if [[ -f "$PID_DIR/backend.pid" ]] && kill -0 "$(cat "$PID_DIR/backend.pid")" 2>/dev/null; then
    echo "Backend já está rodando (PID $(cat "$PID_DIR/backend.pid"))."
  else
    echo "==> Iniciando backend (FastAPI :8000)..."
    _conda
    cd "$BACKEND"
    nohup uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 \
      >"$LOG_DIR/backend.log" 2>&1 &
    echo $! >"$PID_DIR/backend.pid"
    echo "    PID $(cat "$PID_DIR/backend.pid") — log: $LOG_DIR/backend.log"
  fi

  if [[ -f "$PID_DIR/frontend.pid" ]] && kill -0 "$(cat "$PID_DIR/frontend.pid")" 2>/dev/null; then
    echo "Frontend já está rodando (PID $(cat "$PID_DIR/frontend.pid"))."
  else
    echo "==> Iniciando frontend (Vite :3000, host LAN)..."
    _conda
    cd "$FRONTEND"
    nohup npx vite --host 0.0.0.0 --port 3000 \
      >"$LOG_DIR/frontend.log" 2>&1 &
    echo $! >"$PID_DIR/frontend.pid"
    echo "    PID $(cat "$PID_DIR/frontend.pid") — log: $LOG_DIR/frontend.log"
  fi

  sleep 2
  IP="$(_server_ip)"
  echo ""
  echo "============================================"
  echo "  ForensicAuth — desenvolvimento (LAN)"
  echo "============================================"
  echo "  Local:    http://127.0.0.1:3000"
  echo "  Rede:     http://${IP}:3000"
  echo "  API:      http://${IP}:8000/health"
  echo "  Logs:     $LOG_DIR/"
  echo ""
  echo "  Usuário:  paulo.pmgir (primeiro acesso — definir senha)"
  echo "  Parar:    $0 stop"
  echo "============================================"
}

cmd_stop() {
  for name in frontend backend; do
    pidfile="$PID_DIR/${name}.pid"
    if [[ -f "$pidfile" ]]; then
      pid="$(cat "$pidfile")"
      if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        echo "Parado $name (PID $pid)"
      fi
      rm -f "$pidfile"
    fi
  done
  # Vite/uvicorn filhos
  pkill -f "uvicorn app.main:app.*--port 8000" 2>/dev/null || true
  pkill -f "vite.*--port 3000" 2>/dev/null || true
}

cmd_status() {
  for name in backend frontend; do
    pidfile="$PID_DIR/${name}.pid"
    if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
      echo "$name: rodando (PID $(cat "$pidfile"))"
    else
      echo "$name: parado"
    fi
  done
  IP="$(_server_ip)"
  echo "URL LAN: http://${IP}:3000"
}

cmd_setup() {
  echo "==> Criando ambiente conda '$CONDA_ENV' (se não existir)..."
  if ! conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV"; then
    conda create -y -n "$CONDA_ENV" python=3.11
  fi
  _conda
  echo "==> Instalando dependências Python..."
  pip install -q -r "$ROOT/requirements.txt"
  echo "==> Instalando Node.js (conda-forge)..."
  conda install -y -q -c conda-forge nodejs=20
  echo "==> Instalando dependências frontend..."
  cd "$FRONTEND"
  npm install --silent
  echo "==> Seed usuário admin..."
  cd "$BACKEND"
  python "$ROOT/scripts/seed_users.py"
  echo "Setup concluído. Execute: $0 start"
}

case "${1:-start}" in
  setup) cmd_setup ;;
  start) cmd_start ;;
  stop)  cmd_stop ;;
  status) cmd_status ;;
  *)
    echo "Uso: $0 {setup|start|stop|status}"
    exit 1
    ;;
esac
