"""Adapter — detecção de spoofing de áudio multi-detector (DF Arena + SLS + WeDefense)."""

from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import librosa
import numpy as np

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.audio_spoofing.pipeline import run_audio_spoofing_analysis
from core.legacy.audio_spoofing.runtime import (
    VALID_AUDIO_SPOOFING_ANALYSES,
    runtime_status,
)
from core.progress import pop_progress_callback, report_progress
from core.technique_ids import AUDIO_SPOOFING_DETECTION

logger = logging.getLogger(__name__)

DEFAULT_MAX_DURATION_SECONDS = 90.0

_SCORE_HEADERS = ("Detector", "Score Spoof", "Score Bonafide", "Razao (Log)", "Classificacao", "Dispositivo")


def _write_detector_scores_txt(out_dir: Path, rows: list[list[str]]) -> Path:
    lines = ["\t".join(_SCORE_HEADERS)]
    for row in rows:
        lines.append("\t".join(str(cell) for cell in row))
    path = out_dir / "detector_scores.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class AudioSpoofingAdapter(ForensicPlugin):
    """Detecção de spoofing de áudio com ensemble DF Arena 1B, SLS XLS-R e WeDefense WavLM + MHFA."""

    @property
    def name(self) -> str:
        return AUDIO_SPOOFING_DETECTION

    @property
    def supported_types(self) -> list[str]:
        return ["audio"]

    @property
    def description(self) -> str | None:
        return (
            "Deteccao de spoofing de audio com multiplos detectores "
            "(DF Arena 1B, SLS XLS-R, WeDefense WavLM + MHFA), "
            "janelas de 4s e vetor de escores por detector."
        )

    @classmethod
    def is_runtime_available(cls) -> Tuple[bool, str]:
        return runtime_status()

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        ok, reason = runtime_status()
        if not ok:
            return False, reason

        window_seconds = parameters.get("window_seconds", 4.0)
        try:
            window_seconds = float(window_seconds)
        except (TypeError, ValueError):
            return False, "window_seconds deve ser um numero positivo"
        if not 1.0 <= window_seconds <= 60.0:
            return False, "window_seconds deve estar entre 1 e 60"

        max_duration = parameters.get("max_duration_seconds", DEFAULT_MAX_DURATION_SECONDS)
        try:
            max_duration = float(max_duration)
        except (TypeError, ValueError):
            return False, "max_duration_seconds deve ser um numero positivo"
        if not 10.0 <= max_duration <= 300.0:
            return False, "max_duration_seconds deve estar entre 10 e 300"

        selected = parameters.get("selected_analyses")
        if selected is not None:
            if not isinstance(selected, list):
                return False, "selected_analyses deve ser uma lista"
            normalized = {str(item).strip() for item in selected if str(item).strip()}
            if not normalized:
                return False, "Selecione pelo menos um detector de spoofing"
            invalid = sorted(normalized - VALID_AUDIO_SPOOFING_ANALYSES)
            if invalid:
                return False, "Detectores invalidos: " + ", ".join(invalid)
            from core.legacy.audio_spoofing.runtime import detector_runtime_status

            missing: list[str] = []
            for detector_id in sorted(normalized):
                det_ok, det_reason = detector_runtime_status(detector_id)
                if not det_ok:
                    missing.append(f"{detector_id}: {det_reason}")
            if missing:
                return False, "Detectores indisponiveis: " + "; ".join(missing)

        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        ok, reason = runtime_status()
        if not ok:
            return {
                "success": False,
                "error": reason,
                "adapter": AUDIO_SPOOFING_DETECTION,
                "status": "unavailable",
            }

        try:
            report_progress(on_progress, 5, "Carregando audio de evidencia")
            audio, sr = librosa.load(evidence_path, sr=None, mono=True)
            if audio is None or len(audio) == 0:
                return {
                    "success": False,
                    "error": "FAILED_TO_LOAD_AUDIO",
                    "message": "Nao foi possivel carregar o audio de evidencia.",
                    "adapter": AUDIO_SPOOFING_DETECTION,
                }

            window_seconds = float(parameters.get("window_seconds", 4.0))
            max_duration_seconds = float(parameters.get("max_duration_seconds", DEFAULT_MAX_DURATION_SECONDS))
            selected_analyses = parameters.get("selected_analyses")

            original_duration_seconds = len(audio) / sr
            max_samples = int(sr * max_duration_seconds)
            if len(audio) > max_samples:
                audio = audio[:max_samples]
                truncated = True
            else:
                truncated = False
            analyzed_duration_seconds = len(audio) / sr

            report_progress(on_progress, 15, "Executando detectores de spoofing")
            analysis = run_audio_spoofing_analysis(
                audio=np.asarray(audio, dtype=np.float32),
                sr=int(sr),
                window_seconds=window_seconds,
                selected_analyses=selected_analyses,
                on_progress=on_progress,
            )

            report_progress(on_progress, 85, "Gerando artefatos")
            out_dir = job_artifact_dir(parameters, fallback_subdir="audio_spoofing_tmp")
            out_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

            plot_by_detector = analysis.get("plot_by_detector", {})
            primary_plot_key = analysis["selected_analyses"][0] if analysis.get("selected_analyses") else None
            primary_plot = plot_by_detector.get(primary_plot_key, {}) if primary_plot_key else {}
            plot_data = {
                **primary_plot,
                "duration_seconds": round(analyzed_duration_seconds, 3),
                "original_duration_seconds": round(original_duration_seconds, 3),
                "max_duration_seconds": max_duration_seconds,
                "truncated": truncated,
                "plot_by_detector": plot_by_detector,
            }
            plot_path = out_dir / f"audio_spoofing_plot_{stamp}.json"
            plot_path.write_text(json.dumps(plot_data, indent=2), encoding="utf-8")

            details_payload = {
                **analysis,
                "per_detector": analysis.get("per_detector", {}),
                "duration_seconds": plot_data["duration_seconds"],
                "original_duration_seconds": plot_data["original_duration_seconds"],
                "max_duration_seconds": max_duration_seconds,
                "truncated": truncated,
                "window_seconds": window_seconds,
            }
            details_path = out_dir / f"audio_spoofing_details_{stamp}.json"
            details_path.write_text(json.dumps(details_payload, indent=2), encoding="utf-8")

            scores_path = _write_detector_scores_txt(out_dir, analysis["individual_results"])

            report_progress(on_progress, 100, "Concluido")

            return {
                "success": True,
                "adapter": AUDIO_SPOOFING_DETECTION,
                "status": "completed",
                "label": analysis["label"],
                "score_spoof": analysis["score_spoof"],
                "score_bonafide": analysis["score_bonafide"],
                "spoof_logit": analysis.get("spoof_logit"),
                "bonafide_logit": analysis.get("bonafide_logit"),
                "window_count": analysis.get("window_count", 0),
                "window_seconds": window_seconds,
                "duration_seconds": plot_data["duration_seconds"],
                "original_duration_seconds": plot_data["original_duration_seconds"],
                "max_duration_seconds": plot_data["max_duration_seconds"],
                "truncated": plot_data["truncated"],
                "inference_device": analysis.get("inference_device", "cpu"),
                "selected_analyses": analysis.get("selected_analyses", selected_analyses),
                "individual_results": analysis["individual_results"],
                "detector_scores": analysis.get("detector_scores", {}),
                "plot_data": plot_data,
                "plot_by_detector": plot_by_detector,
                "plot_filename": plot_path.name,
                "details_filename": details_path.name,
                "detector_scores_filename": scores_path.name,
                "detector_scores_txt_path": str(scores_path),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as exc:
            error_message = str(exc) or repr(exc)
            logger.exception("Erro no audio_spoofing_detection: %s", error_message)
            return {
                "success": False,
                "error": f"ADAPTER_ERROR: {error_message}",
                "message": error_message,
                "traceback": traceback.format_exc(),
                "adapter": AUDIO_SPOOFING_DETECTION,
            }
