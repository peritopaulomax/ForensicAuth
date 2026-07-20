#!/usr/bin/env bash
# Aguarda fim do augmentation e dispara run_audio_typicality_pipeline.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/outputs/lr_calibration/audio_spoofing/augmentation_pipeline.log"
SUMMARY="$ROOT/outputs/lr_calibration/audio_spoofing/samples/augmented/summary.json"
MANIFEST="$ROOT/outputs/lr_calibration/audio_spoofing/samples/augmented/manifest.csv"
NEXT="$ROOT/scripts/run_audio_typicality_pipeline.sh"
WATCH_LOG="$ROOT/outputs/lr_calibration/audio_spoofing/watch_augmentation.log"
EXPECTED_SOURCES=34398
EXPECTED_AUG_ROWS=$((EXPECTED_SOURCES * 4))

exec > >(tee -a "$WATCH_LOG") 2>&1
echo "=== $(date -Is) Watcher iniciado ==="

while true; do
  if grep -q "FIM etapa 1" "$LOG" 2>/dev/null; then
    echo "$(date -Is) Detectado FIM etapa 1 no log."
    break
  fi
  if [[ -f "$SUMMARY" ]]; then
    echo "$(date -Is) Detectado summary.json."
    break
  fi
  if ! pgrep -f "augment_audio_lr_dataset.py" >/dev/null 2>&1; then
    if [[ -f "$MANIFEST" ]]; then
      rows=$(($(wc -l < "$MANIFEST") - 1))
      if (( rows >= EXPECTED_AUG_ROWS - 500 )); then
        echo "$(date -Is) Processo terminou com manifest ~OK ($rows linhas)."
        break
      fi
    fi
  fi
  tail -1 "$LOG" 2>/dev/null || true
  sleep 120
done

echo "$(date -Is) Iniciando pipeline tipicidade..."
exec bash "$NEXT"
