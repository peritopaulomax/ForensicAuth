#!/usr/bin/env bash
# Dev stack: Postgres+Redis (compose dev), API, worker-cpu, worker-gpu.
# Uso: ./scripts/dev-stack.sh setup | start | stop | status
set -euo pipefail

export NO_PROXY="localhost,127.0.0.1,10.0.0.0/8,192.168.0.0/16"
export no_proxy="$NO_PROXY"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY 2>/dev/null || true

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/src/backend"
FRONTEND="$ROOT/src/frontend"
PID_DIR="$ROOT/.dev-pids"
LOG_DIR="$ROOT/.dev-logs"
CONDA_ENV="${FORENSICAUTH_CONDA_ENV:-va-suite}"

mkdir -p "$PID_DIR" "$LOG_DIR"
mkdir -p "$ROOT/uploads-dev" "$ROOT/results-dev" "$ROOT/derivatives-dev" \
         "$ROOT/peritus_cases-dev" "$ROOT/models"

_conda() {
  # shellcheck disable=SC1091
  source "$(conda info --base)/etc/profile.d/conda.sh"
  conda activate "$CONDA_ENV"
}

_server_ip() {
  hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1"
}

_infra_up() {
  echo "==> Postgres + Redis (docker compose dev)..."
  docker compose -f "$ROOT/docker-compose.dev.yml" -p forensicauth-dev up -d
}

cmd_setup() {
  _infra_up
  if ! conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV"; then
    conda create -y -n "$CONDA_ENV" python=3.11
  fi
  _conda
  pip install -q -r "$ROOT/requirements.txt"
  if [[ -f "$ROOT/requirements-gpu.txt" ]]; then
    pip install -q -r "$ROOT/requirements-gpu.txt" || true
  fi
  cd "$BACKEND"
  python "$ROOT/scripts/seed_users.py" 2>/dev/null || true
  echo "Setup concluido."
}

_start_background() {
  local name="$1"
  local pidfile="$PID_DIR/${name}.pid"
  local logfile="$LOG_DIR/${name}.log"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "$name ja rodando (PID $(cat "$pidfile"))"
    return 0
  fi
  shift
  nohup "$@" >"$logfile" 2>&1 &
  echo $! >"$pidfile"
  echo "$name PID $(cat "$pidfile") — log: $logfile"
}

cmd_start() {
  _infra_up
  _conda

  echo "==> API (uvicorn)..."
  (
    cd "$BACKEND"
    export FORENSICAUTH_PROCESS_ROLE=api GPU_AVAILABLE=false ML_WARMUP_ON_STARTUP=false
    _start_background api uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
  )

  echo "==> worker-cpu..."
  (
    cd "$BACKEND"
    export FORENSICAUTH_PROCESS_ROLE=worker-cpu GPU_AVAILABLE=false FORENSICAUTH_WORKER_QUEUE=celery
    export ML_WARMUP_ON_STARTUP=false
    _start_background worker-cpu celery -A app.celery_app worker -Q celery -c 4 -n "cpu@%h" --loglevel=info
  )

  echo "==> worker-gpu..."
  (
    cd "$BACKEND"
    export FORENSICAUTH_PROCESS_ROLE=worker-gpu GPU_AVAILABLE=true FORENSICAUTH_WORKER_QUEUE=gpu
    export ML_WARMUP_ON_STARTUP=true SYNTHETIC_KEEP_RESIDENT=true
    _start_background worker-gpu celery -A app.celery_app worker -Q gpu -c 1 -n "gpu-local@%h" --loglevel=info
  )

  if [[ "${DEV_STACK_FRONTEND:-1}" == "1" ]]; then
    echo "==> frontend..."
    (
      cd "$FRONTEND"
      _start_background frontend npx vite --host 0.0.0.0 --port 3000
    )
  fi

  sleep 2
  IP="$(_server_ip)"
  echo ""
  echo "============================================"
  echo "  VA Suite dev stack"
  echo "  API:      http://${IP}:8000/health"
  echo "  Frontend: http://${IP}:3000"
  echo "  Logs:     $LOG_DIR/"
  echo "  Parar:    $0 stop"
  echo "============================================"
}

cmd_stop() {
  for name in frontend worker-gpu worker-cpu api; do
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
  pkill -f "uvicorn app.main:app.*--port 8000" 2>/dev/null || true
  pkill -f "celery -A app.celery_app worker" 2>/dev/null || true
  pkill -f "vite.*--port 3000" 2>/dev/null || true
}

cmd_status() {
  for name in api worker-cpu worker-gpu frontend; do
    pidfile="$PID_DIR/${name}.pid"
    if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
      echo "$name: rodando (PID $(cat "$pidfile"))"
    else
      echo "$name: parado"
    fi
  done
}

case "${1:-start}" in
  setup) cmd_setup ;;
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  *)
    echo "Uso: $0 {setup|start|stop|status}"
    exit 1
    ;;
esac
