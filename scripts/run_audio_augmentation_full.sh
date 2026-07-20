#!/usr/bin/env bash
# Etapa 1 apenas: gerar WAVs aumentados + manifest (sem scoring/merge).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate va-suite

LOG="$ROOT/outputs/lr_calibration/audio_spoofing/augmentation_pipeline.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== $(date -Is) INICIO etapa 1 (augmentation WAVs) ==="
echo "ffmpeg: $(command -v ffmpeg)"

python scripts/augment_audio_lr_dataset.py \
  --score-matrix "$ROOT/outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full.csv" \
  --out-dir "$ROOT/outputs/lr_calibration/audio_spoofing/samples/augmented" \
  --resume

echo "=== $(date -Is) FIM etapa 1 — parado (sem scoring/merge) ==="
