#!/usr/bin/env bash
# Recursive completion loop: protocol audit -> score topup -> augment -> extract -> merge -> gate
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate va-suite

MAX_ITERS="${MAX_ITERS:-10}"
LOG="$ROOT/outputs/lr_calibration/audio_spoofing/completion_loop.log"
BASE="$ROOT/outputs/lr_calibration/audio_spoofing"
MANIFEST="$BASE/samples/full/manifest.csv"
SCORE_MATRIX="$BASE/score_matrices/lr_scores_balanced_full.csv"

exec > >(tee -a "$LOG") 2>&1

log() { echo "=== $(date -Is) $* ==="; }

run_gate() {
  local iter="$1"
  python scripts/audio_lr_completion_gate.py --loop-iteration "$iter" || return 1
}

log "INICIO completion loop (max_iters=$MAX_ITERS)"

for iter in $(seq 1 "$MAX_ITERS"); do
  log "LOOP iteracao $iter/$MAX_ITERS"

  if [[ "$iter" -eq 1 ]] || [[ ! -f "$ROOT/outputs/lr_calibration/audio_spoofing/inventory/protocol_pool_audit.csv" ]]; then
    log "Fase 1 — protocol pool audit"
    python scripts/audit_protocol_pools.py
  else
    log "Fase 1 — protocol pool audit (skip, cache ok)"
  fi

  log "Fase 2 — unit tests sample_id"
  PYTHONPATH=src/backend pytest tests/unit/test_audio_representations.py tests/unit/test_audio_lr_disk_verify.py -q

  log "Fase 3 — score matrix resume + topup"
  if [[ -f "$MANIFEST" ]]; then
    python scripts/run_audio_spoofing_score_matrix.py \
      --manifest "$MANIFEST" \
      --out "$SCORE_MATRIX" \
      --resume || true
  fi
  python scripts/topup_score_matrix_to_target.py

  log "Fase 4 — augment resume"
  python scripts/augment_audio_lr_dataset.py \
    --score-matrix "$SCORE_MATRIX" \
    --out-dir "$BASE/samples/augmented" \
    --resume

  log "Fase 5 — extract originals"
  python scripts/extract_audio_representations.py --source originals --resume

  log "Fase 6 — extract augmented"
  python scripts/extract_audio_representations.py --source augmented --resume

  log "Fase 7 — merge"
  python scripts/merge_audio_representations.py

  log "Fase 8 — disk audit"
  python scripts/inventory_audio_lr_disk_audit.py

  if run_gate "$iter"; then
    log "GATE VERDE na iteracao $iter"
    PYTHONPATH=src/backend pytest tests/integration/test_audio_lr_disk_completion_gate.py -q
    log "FIM completion loop — SUCESSO"
    exit 0
  fi

  log "GATE VERMELHO — rearrumando na proxima iteracao"
  # Optional repair for orphaned CSV rows without npy
  if [[ -f scripts/repair_audio_augmented_representations.py ]]; then
    python scripts/repair_audio_augmented_representations.py --dry-run 2>/dev/null | tail -5 || true
  fi
done

log "FIM completion loop — MAX_ITERS atingido sem gate verde"
python scripts/audio_lr_completion_gate.py --loop-iteration "$MAX_ITERS" || true
exit 1
