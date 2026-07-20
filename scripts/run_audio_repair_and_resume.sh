#!/usr/bin/env bash
# Recuperação pós-bug sample_id: reparar metadados + extrair só o que falta + merge.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate va-suite

LOG="$ROOT/outputs/lr_calibration/audio_spoofing/repair_and_resume_pipeline.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== $(date -Is) INICIO repair + resume augmented representations ==="

echo "--- Etapa A: corrigir sample_id / renomear embeddings (sem GPU) ---"
python scripts/repair_audio_augmented_representations.py

echo "--- Etapa B: extrair apenas linhas ainda ausentes (GPU) ---"
python scripts/extract_audio_representations.py --source augmented --resume

echo "--- Etapa C: merge originals + augmented ---"
python scripts/merge_audio_representations.py

echo "=== $(date -Is) FIM repair + resume ==="
