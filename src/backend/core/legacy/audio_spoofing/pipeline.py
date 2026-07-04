"""Multi-detector audio spoofing pipeline (DF Arena + SLS XLS-R + WeDefense)."""

from __future__ import annotations

import logging
import math
from typing import Any, Callable, Optional

import numpy as np

from core.gpu_inference import device_display_label, resolve_inference_device
from core.legacy.audio_spoofing.runtime import (
    AUDIO_SPOOFING_ANALYSIS_DF_ARENA,
    AUDIO_SPOOFING_ANALYSIS_SLS_XLSR,
    AUDIO_SPOOFING_ANALYSIS_WEDEFENSE,
    DEFAULT_AUDIO_SPOOFING_ANALYSES,
    DETECTOR_DISPLAY,
    VALID_AUDIO_SPOOFING_ANALYSES,
    detector_runtime_status,
)
from core.legacy.df_arena import df_arena_pipeline as df_arena
from core.legacy.sls_spoofing import sls_pipeline as sls
from core.legacy.wedefense_spoofing import wedefense_pipeline as wedefense
from core.progress import report_progress

logger = logging.getLogger(__name__)

ProgressFn = Optional[Callable[[int, str], None]]
UNCERTAINTY_THRESHOLD = 0.65


def _normalize_selected(selected_analyses: Optional[list[str] | tuple[str, ...] | set[str]]) -> set[str]:
    if selected_analyses is None:
        return set(DEFAULT_AUDIO_SPOOFING_ANALYSES)
    return {str(item).strip() for item in selected_analyses if str(item).strip()}


def _classification_label(spoof_prob: float, bonafide_prob: float) -> str:
    if spoof_prob > UNCERTAINTY_THRESHOLD:
        return "Spoof"
    if bonafide_prob > UNCERTAINTY_THRESHOLD:
        return "Bonafide"
    return "Incerto"


def _score_row(
    detector_id: str,
    spoof_prob: float,
    bonafide_prob: float,
    device_label: str,
) -> list[str]:
    razao = bonafide_prob / spoof_prob if spoof_prob > 1e-9 else float("inf")
    log_ratio = f"{math.log10(razao):.2f}" if math.isfinite(razao) else "inf"
    return [
        DETECTOR_DISPLAY.get(detector_id, detector_id),
        f"{spoof_prob:.4f}",
        f"{bonafide_prob:.4f}",
        log_ratio,
        _classification_label(spoof_prob, bonafide_prob),
        device_label,
    ]


def run_audio_spoofing_analysis(
    audio: np.ndarray,
    sr: int,
    *,
    window_seconds: float = 4.0,
    selected_analyses: Optional[list[str] | tuple[str, ...] | set[str]] = None,
    on_progress: ProgressFn = None,
) -> dict[str, Any]:
    """Run selected spoofing detectors and return structured per-detector scores."""
    selected = _normalize_selected(selected_analyses)
    invalid = sorted(selected - VALID_AUDIO_SPOOFING_ANALYSES)
    if invalid:
        raise ValueError("Detectores invalidos: " + ", ".join(invalid))
    if not selected:
        raise ValueError("Selecione pelo menos um detector de spoofing")

    individual_results: list[list[str]] = []
    detector_scores: dict[str, dict[str, Any]] = {}
    per_detector: dict[str, dict[str, Any]] = {}
    plot_by_detector: dict[str, dict[str, Any]] = {}
    devices: list[str] = []
    unavailable: list[str] = []

    total = len(selected)
    step = 0

    if AUDIO_SPOOFING_ANALYSIS_DF_ARENA in selected:
        step += 1
        ok, reason = detector_runtime_status(AUDIO_SPOOFING_ANALYSIS_DF_ARENA)
        if not ok:
            logger.warning("DF Arena indisponivel: %s", reason)
            unavailable.append(f"DF Arena: {reason}")
        else:
            pct = 20 + int(50 * step / max(total, 1))
            report_progress(on_progress, pct, "Inferindo DF Arena 1B…")
            result = df_arena.infer_df_arena_windows(
                audio=np.asarray(audio, dtype=np.float32),
                sr=int(sr),
                window_seconds=window_seconds,
            )
            agg = result["aggregated"]
            device_label = device_display_label(result.get("inference_device", "cpu"))
            devices.append(device_label)
            per_detector[AUDIO_SPOOFING_ANALYSIS_DF_ARENA] = result
            plot_by_detector[AUDIO_SPOOFING_ANALYSIS_DF_ARENA] = {
                "centers": [w["center_seconds"] for w in result["windows"]],
                "spoof_probs": [w["spoof_prob"] for w in result["windows"]],
                "bonafide_probs": [w["bonafide_prob"] for w in result["windows"]],
                "window_seconds": window_seconds,
                "detector": AUDIO_SPOOFING_ANALYSIS_DF_ARENA,
            }
            row = _score_row(
                AUDIO_SPOOFING_ANALYSIS_DF_ARENA,
                float(agg["spoof_prob"]),
                float(agg["bonafide_prob"]),
                device_label,
            )
            individual_results.append(row)
            detector_scores[AUDIO_SPOOFING_ANALYSIS_DF_ARENA] = {
                "spoof_prob": float(agg["spoof_prob"]),
                "bonafide_prob": float(agg["bonafide_prob"]),
                "spoof_logit": float(agg["spoof_logit"]),
                "bonafide_logit": float(agg["bonafide_logit"]),
                "label": agg["label"],
                "decision": row[4],
                "device": device_label,
                "window_count": result["window_count"],
            }

    if AUDIO_SPOOFING_ANALYSIS_SLS_XLSR in selected:
        step += 1
        ok, reason = detector_runtime_status(AUDIO_SPOOFING_ANALYSIS_SLS_XLSR)
        if not ok:
            logger.warning("SLS indisponivel: %s", reason)
            unavailable.append(f"SLS XLS-R: {reason}")
        else:
            pct = 20 + int(50 * step / max(total, 1))
            report_progress(on_progress, pct, "Inferindo SLS XLS-R…")
            result = sls.infer_sls_windows(
                audio=np.asarray(audio, dtype=np.float32),
                sr=int(sr),
                window_seconds=window_seconds,
            )
            agg = result["aggregated"]
            device_label = device_display_label(result.get("inference_device", "cpu"))
            devices.append(device_label)
            per_detector[AUDIO_SPOOFING_ANALYSIS_SLS_XLSR] = result
            plot_by_detector[AUDIO_SPOOFING_ANALYSIS_SLS_XLSR] = {
                "centers": [w["center_seconds"] for w in result["windows"]],
                "spoof_probs": [w["spoof_prob"] for w in result["windows"]],
                "bonafide_probs": [w["bonafide_prob"] for w in result["windows"]],
                "window_seconds": window_seconds,
                "detector": AUDIO_SPOOFING_ANALYSIS_SLS_XLSR,
            }
            row = _score_row(
                AUDIO_SPOOFING_ANALYSIS_SLS_XLSR,
                float(agg["spoof_prob"]),
                float(agg["bonafide_prob"]),
                device_label,
            )
            individual_results.append(row)
            detector_scores[AUDIO_SPOOFING_ANALYSIS_SLS_XLSR] = {
                "spoof_prob": float(agg["spoof_prob"]),
                "bonafide_prob": float(agg["bonafide_prob"]),
                "spoof_logit": float(agg["spoof_logit"]),
                "bonafide_logit": float(agg["bonafide_logit"]),
                "bonafide_score": float(agg.get("bonafide_score", agg["bonafide_logit"])),
                "label": agg["label"],
                "decision": row[4],
                "device": device_label,
                "window_count": result["window_count"],
            }

    if AUDIO_SPOOFING_ANALYSIS_WEDEFENSE in selected:
        step += 1
        ok, reason = detector_runtime_status(AUDIO_SPOOFING_ANALYSIS_WEDEFENSE)
        if not ok:
            logger.warning("WeDefense indisponivel: %s", reason)
            unavailable.append(f"WeDefense: {reason}")
        else:
            pct = 20 + int(50 * step / max(total, 1))
            report_progress(on_progress, pct, "Inferindo WeDefense WavLM + MHFA…")
            result = wedefense.infer_wedefense_windows(
                audio=np.asarray(audio, dtype=np.float32),
                sr=int(sr),
                window_seconds=window_seconds,
            )
            agg = result["aggregated"]
            device_label = device_display_label(result.get("inference_device", "cpu"))
            devices.append(device_label)
            per_detector[AUDIO_SPOOFING_ANALYSIS_WEDEFENSE] = result
            plot_by_detector[AUDIO_SPOOFING_ANALYSIS_WEDEFENSE] = {
                "centers": [w["center_seconds"] for w in result["windows"]],
                "spoof_probs": [w["spoof_prob"] for w in result["windows"]],
                "bonafide_probs": [w["bonafide_prob"] for w in result["windows"]],
                "window_seconds": window_seconds,
                "detector": AUDIO_SPOOFING_ANALYSIS_WEDEFENSE,
            }
            row = _score_row(
                AUDIO_SPOOFING_ANALYSIS_WEDEFENSE,
                float(agg["spoof_prob"]),
                float(agg["bonafide_prob"]),
                device_label,
            )
            individual_results.append(row)
            detector_scores[AUDIO_SPOOFING_ANALYSIS_WEDEFENSE] = {
                "spoof_prob": float(agg["spoof_prob"]),
                "bonafide_prob": float(agg["bonafide_prob"]),
                "spoof_logit": float(agg["spoof_logit"]),
                "bonafide_logit": float(agg["bonafide_logit"]),
                "bonafide_score": float(agg.get("bonafide_score", agg["bonafide_logit"])),
                "label": agg["label"],
                "decision": row[4],
                "device": device_label,
                "window_count": result["window_count"],
            }

    if not individual_results:
        if unavailable:
            raise RuntimeError(
                "Nenhum detector selecionado produziu resultado. Indisponiveis: "
                + "; ".join(unavailable)
            )
        raise RuntimeError("Nenhum detector de spoofing produziu resultado")

    report_progress(on_progress, 78, "Agregando escores dos detectores…")

    # Primary aggregated view: first selected detector with results, else mean of probs
    primary_id = next(iter(detector_scores))
    primary = detector_scores[primary_id]
    inference_device = devices[0] if len(devices) == 1 else resolve_inference_device().type

    return {
        "individual_results": individual_results,
        "detector_scores": detector_scores,
        "per_detector": per_detector,
        "plot_by_detector": plot_by_detector,
        "selected_analyses": sorted(selected),
        "inference_device": inference_device,
        "label": primary["label"],
        "score_spoof": primary["spoof_prob"],
        "score_bonafide": primary["bonafide_prob"],
        "spoof_logit": primary.get("spoof_logit"),
        "bonafide_logit": primary.get("bonafide_logit"),
        "window_count": primary.get("window_count", 0),
    }
