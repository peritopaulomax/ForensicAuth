#!/usr/bin/env bash
# Corrige sample_id (stem com pontos) + repara CSV + extrai faltantes + merge.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate va-suite

LOG="$ROOT/outputs/lr_calibration/audio_spoofing/fix_stem_and_complete.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== $(date -Is) INICIO fix_stem_and_complete ==="

python scripts/repair_audio_augmented_representations.py

python scripts/augment_audio_lr_dataset.py \
  --score-matrix "$ROOT/outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full.csv" \
  --out-dir "$ROOT/outputs/lr_calibration/audio_spoofing/samples/augmented" \
  --rebuild-manifest

python scripts/extract_audio_representations.py --source augmented --resume

MANIFEST_ROWS="$(($(wc -l < "$ROOT/outputs/lr_calibration/audio_spoofing/samples/augmented/manifest.csv") - 1))"
REP_ROWS="$(python3 -c "import pandas as pd; print(len(pd.read_csv('$ROOT/outputs/lr_calibration/audio_spoofing/representations/augmented/representations.csv', usecols=['sample_id'])))")"
echo "[check] manifest_unique_expected~127088 manifest_rows=$MANIFEST_ROWS rep_rows=$REP_ROWS"

if [[ "$REP_ROWS" -lt "$((MANIFEST_ROWS - 500))" ]]; then
  echo "=== $(date -Is) extract pass extra ==="
  python scripts/extract_audio_representations.py --source augmented --resume
fi

python scripts/merge_audio_representations.py
python scripts/inventory_audio_lr_typicality.py

echo "=== $(date -Is) FIM fix_stem_and_complete ==="
