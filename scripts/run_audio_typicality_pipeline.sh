#!/usr/bin/env bash
# Pipeline offline: manifest completo + extrair scores+embeddings (aug + orig) + merge.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate va-suite

LOG="$ROOT/outputs/lr_calibration/audio_spoofing/typicality_pipeline.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== $(date -Is) INICIO pipeline tipicidade (manifest + extracao + merge) ==="

python scripts/augment_audio_lr_dataset.py \
  --score-matrix "$ROOT/outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full.csv" \
  --out-dir "$ROOT/outputs/lr_calibration/audio_spoofing/samples/augmented" \
  --rebuild-manifest

python scripts/augment_audio_lr_dataset.py \
  --score-matrix "$ROOT/outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full.csv" \
  --out-dir "$ROOT/outputs/lr_calibration/audio_spoofing/samples/augmented" \
  --resume

python scripts/extract_audio_representations.py \
  --source augmented \
  --resume

python scripts/extract_audio_representations.py \
  --source originals \
  --resume

python scripts/merge_audio_representations.py

echo "=== $(date -Is) FIM pipeline tipicidade ==="
