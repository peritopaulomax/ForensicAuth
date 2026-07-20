#!/usr/bin/env bash
# Completa pipeline LR tipicidade: augment WAVs (CPU) || extract emb (GPU) → merge → inventário.
# Idempotente: seguro reexecutar com --resume em cada etapa.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate va-suite

LOG="$ROOT/outputs/lr_calibration/audio_spoofing/finish_parallel_pipeline.log"
exec > >(tee -a "$LOG") 2>&1

SCORE_MATRIX="$ROOT/outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full.csv"
AUG_DIR="$ROOT/outputs/lr_calibration/audio_spoofing/samples/augmented"
MANIFEST="$AUG_DIR/manifest.csv"

echo "=== $(date -Is) INICIO finish_parallel_pipeline ==="

wait_pid() {
  local label="$1"
  local pid="$2"
  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
    echo "[$label] pid $pid nao esta rodando — seguindo"
    return 0
  fi
  echo "[$label] aguardando pid $pid ..."
  while kill -0 "$pid" 2>/dev/null; do
    sleep 30
  done
  echo "[$label] pid $pid concluido"
}

# --- Etapa A: augment WAVs (CPU/ffmpeg) em background se nao estiver rodando ---
AUG_PID=""
if pgrep -f "python scripts/augment_audio_lr_dataset.py" >/dev/null 2>&1; then
  AUG_PID="$(pgrep -f "python scripts/augment_audio_lr_dataset.py" | head -1)"
  echo "[augment] ja rodando pid=$AUG_PID"
else
  echo "[augment] iniciando augment_audio_lr_dataset.py --resume"
  python scripts/augment_audio_lr_dataset.py \
    --score-matrix "$SCORE_MATRIX" \
    --out-dir "$AUG_DIR" \
    --resume &
  AUG_PID=$!
fi

# --- Etapa B: extract embeddings (GPU) em background se nao estiver rodando ---
EXT_PID=""
if pgrep -f "python scripts/extract_audio_representations.py --source augmented" >/dev/null 2>&1; then
  EXT_PID="$(pgrep -f "python scripts/extract_audio_representations.py --source augmented" | head -1)"
  echo "[extract] ja rodando pid=$EXT_PID"
else
  echo "[extract] iniciando extract_audio_representations.py --source augmented --resume"
  python scripts/extract_audio_representations.py --source augmented --resume &
  EXT_PID=$!
fi

wait_pid "augment" "$AUG_PID"
wait_pid "extract_pass_1" "$EXT_PID"

echo "=== $(date -Is) rebuild manifest apos augment ==="
python scripts/augment_audio_lr_dataset.py \
  --score-matrix "$SCORE_MATRIX" \
  --out-dir "$AUG_DIR" \
  --rebuild-manifest

# --- Etapa C: segunda passagem extract (pega WAVs novos do manifest) ---
echo "=== $(date -Is) extract pass 2 (manifest atualizado) ==="
python scripts/extract_audio_representations.py --source augmented --resume

MANIFEST_ROWS="$(($(wc -l < "$MANIFEST") - 1))"
REP_ROWS="$(($(wc -l < "$ROOT/outputs/lr_calibration/audio_spoofing/representations/augmented/representations.csv") - 1))"
echo "[check] manifest_rows=$MANIFEST_ROWS augmented_rep_rows=$REP_ROWS"

if [[ "$REP_ROWS" -lt "$MANIFEST_ROWS" ]]; then
  echo "=== $(date -Is) extract pass 3 (ainda faltam $((MANIFEST_ROWS - REP_ROWS))) ==="
  python scripts/extract_audio_representations.py --source augmented --resume
  REP_ROWS="$(($(wc -l < "$ROOT/outputs/lr_calibration/audio_spoofing/representations/augmented/representations.csv") - 1))"
fi

echo "=== $(date -Is) merge representations ==="
python scripts/merge_audio_representations.py

echo "=== $(date -Is) inventario ==="
python scripts/inventory_audio_lr_typicality.py

echo "=== $(date -Is) FIM finish_parallel_pipeline ==="
echo "manifest_rows=$MANIFEST_ROWS augmented_rep_rows=$REP_ROWS"
echo "log: $LOG"
