"""Multi-detector audio spoofing pipeline (DF Arena + SLS + WeDefense + TFCL)."""

from __future__ import annotations

import logging
import math
from typing import Any, Callable, Optional

import numpy as np

from core.gpu_inference import device_display_label, resolve_inference_device
from core.progress import report_progress
from forensics.audio_spoofing.runtime import (
    AUDIO_SPOOFING_ANALYSIS_DF_ARENA,
    AUDIO_SPOOFING_ANALYSIS_SLS_XLSR,
    AUDIO_SPOOFING_ANALYSIS_TFCL,
    AUDIO_SPOOFING_ANALYSIS_WEDEFENSE,
    DEFAULT_AUDIO_SPOOFING_ANALYSES,
    DETECTOR_DISPLAY,
    VALID_AUDIO_SPOOFING_ANALYSES,
    detector_runtime_status,
)
from forensics.df_arena import df_arena_pipeline as df_arena
from forensics.sls_spoofing import sls_pipeline as sls
from forensics.tfcl_spoofing import tfcl_pipeline as tfcl
from forensics.wedefense_spoofing import wedefense_pipeline as wedefense

logger = logging.getLogger(__name__)

ProgressFn = Optional[Callable[[int, str], None]]
# Hard label alinhado ao script/artigo TFCL (e convenção ASVspoof soft-score):
# logit_bonafide >= 0 → Bonafide; caso contrário → Spoof. Sem banda "Incerto".
BONAFIDE_LOGIT_THRESHOLD = 0.0


def _normalize_selected(selected_analyses: Optional[list[str] | tuple[str, ...] | set[str]]) -> set[str]:
    if selected_analyses is None:
        return set(DEFAULT_AUDIO_SPOOFING_ANALYSES)
    return {str(item).strip() for item in selected_analyses if str(item).strip()}


def classification_from_bonafide_logit(bonafide_logit: float, *, threshold: float = BONAFIDE_LOGIT_THRESHOLD) -> str:
    """Rótulo hard: score contínuo = logit bonafide (maior favorece bona)."""
    return "Bonafide" if float(bonafide_logit) >= float(threshold) else "Spoof"


def _drop_incomplete_trailing_window(
    audio: np.ndarray,
    sr: int,
    *,
    window_seconds: float,
) -> np.ndarray:
    """Drop a trailing partial window that can break conv backbones (e.g. WeDefense).

    Full windows are unchanged. If the remainder is shorter than one window, it is
    discarded so detectors only see complete ``window_seconds`` chunks.
    """
    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.mean(axis=1).astype(np.float32, copy=False)
    window_samples = int(float(sr) * float(window_seconds))
    if window_samples <= 0 or arr.size < window_samples:
        return arr
    usable = (arr.size // window_samples) * window_samples
    if usable <= 0 or usable == arr.size:
        return arr
    return arr[:usable]


def _score_row(
    detector_id: str,
    spoof_logit: float,
    bonafide_logit: float,
    device_label: str,
) -> list[str]:
    delta = float(bonafide_logit) - float(spoof_logit)
    if math.isfinite(delta):
        log_ratio = f"{delta / math.log(10.0):.2f}"
    else:
        log_ratio = "nan"
    return [
        DETECTOR_DISPLAY.get(detector_id, detector_id),
        f"{float(spoof_logit):.4f}",
        f"{float(bonafide_logit):.4f}",
        log_ratio,
        classification_from_bonafide_logit(bonafide_logit),
        device_label,
    ]


def run_audio_spoofing_analysis(
    audio: np.ndarray,
    sr: int,
    *,
    window_seconds: float = 4.0,
    selected_analyses: Optional[list[str] | tuple[str, ...] | set[str]] = None,
    on_progress: ProgressFn = None,
    return_embedding: bool = False,
) -> dict[str, Any]:
    """Run selected spoofing detectors and return structured per-detector scores."""
    selected = _normalize_selected(selected_analyses)
    invalid = sorted(selected - VALID_AUDIO_SPOOFING_ANALYSES)
    if invalid:
        raise ValueError("Detectores invalidos: " + ", ".join(invalid))
    if not selected:
        raise ValueError("Selecione pelo menos um detector de spoofing")

    audio = _drop_incomplete_trailing_window(audio, sr, window_seconds=window_seconds)

    individual_results: list[list[str]] = []
    detector_scores: dict[str, dict[str, Any]] = {}
    per_detector: dict[str, dict[str, Any]] = {}
    plot_by_detector: dict[str, dict[str, Any]] = {}
    devices: list[str] = []
    unavailable: list[str] = []

    total = len(selected)
    step = 0

    def _record(detector_id: str, result: dict[str, Any], progress_label: str) -> None:
        nonlocal step
        step += 1
        pct = 20 + int(50 * step / max(total, 1))
        report_progress(on_progress, pct, progress_label)
        agg = result["aggregated"]
        device_label = device_display_label(result.get("inference_device", "cpu"))
        devices.append(device_label)
        per_detector[detector_id] = result
        plot_by_detector[detector_id] = {
            "centers": [w["center_seconds"] for w in result["windows"]],
            "spoof_probs": [w["spoof_prob"] for w in result["windows"]],
            "bonafide_probs": [w["bonafide_prob"] for w in result["windows"]],
            "window_seconds": window_seconds,
            "detector": detector_id,
        }
        spoof_logit = float(agg["spoof_logit"])
        bonafide_logit = float(agg["bonafide_logit"])
        decision = classification_from_bonafide_logit(bonafide_logit)
        row = _score_row(detector_id, spoof_logit, bonafide_logit, device_label)
        individual_results.append(row)
        detector_scores[detector_id] = {
            "spoof_prob": float(agg["spoof_prob"]),
            "bonafide_prob": float(agg["bonafide_prob"]),
            "spoof_logit": spoof_logit,
            "bonafide_logit": bonafide_logit,
            "bonafide_score": float(agg.get("bonafide_score", bonafide_logit)),
            "label": decision.lower(),
            "decision": decision,
            "device": device_label,
            "window_count": result["window_count"],
        }
        if return_embedding and "embedding" in result:
            detector_scores[detector_id]["embedding"] = result["embedding"]
            detector_scores[detector_id]["embedding_dim"] = result.get("embedding_dim")

    if AUDIO_SPOOFING_ANALYSIS_DF_ARENA in selected:
        ok, reason = detector_runtime_status(AUDIO_SPOOFING_ANALYSIS_DF_ARENA)
        if not ok:
            logger.warning("DF Arena indisponivel: %s", reason)
            unavailable.append(f"DF Arena: {reason}")
        else:
            result = df_arena.infer_df_arena_windows(
                audio=np.asarray(audio, dtype=np.float32),
                sr=int(sr),
                window_seconds=window_seconds,
                return_embedding=return_embedding,
            )
            _record(AUDIO_SPOOFING_ANALYSIS_DF_ARENA, result, "Inferindo DF Arena 1B…")

    if AUDIO_SPOOFING_ANALYSIS_SLS_XLSR in selected:
        ok, reason = detector_runtime_status(AUDIO_SPOOFING_ANALYSIS_SLS_XLSR)
        if not ok:
            logger.warning("SLS indisponivel: %s", reason)
            unavailable.append(f"SLS XLS-R: {reason}")
        else:
            result = sls.infer_sls_windows(
                audio=np.asarray(audio, dtype=np.float32),
                sr=int(sr),
                window_seconds=window_seconds,
                return_embedding=return_embedding,
            )
            _record(AUDIO_SPOOFING_ANALYSIS_SLS_XLSR, result, "Inferindo SLS XLS-R…")

    if AUDIO_SPOOFING_ANALYSIS_WEDEFENSE in selected:
        ok, reason = detector_runtime_status(AUDIO_SPOOFING_ANALYSIS_WEDEFENSE)
        if not ok:
            logger.warning("WeDefense indisponivel: %s", reason)
            unavailable.append(f"WeDefense: {reason}")
        else:
            result = wedefense.infer_wedefense_windows(
                audio=np.asarray(audio, dtype=np.float32),
                sr=int(sr),
                window_seconds=window_seconds,
                return_embedding=return_embedding,
            )
            _record(AUDIO_SPOOFING_ANALYSIS_WEDEFENSE, result, "Inferindo WeDefense WavLM + MHFA…")

    if AUDIO_SPOOFING_ANALYSIS_TFCL in selected:
        ok, reason = detector_runtime_status(AUDIO_SPOOFING_ANALYSIS_TFCL)
        if not ok:
            logger.warning("TFCL indisponivel: %s", reason)
            unavailable.append(f"TFCL: {reason}")
        else:
            result = tfcl.infer_tfcl_windows(
                audio=np.asarray(audio, dtype=np.float32),
                sr=int(sr),
                window_seconds=window_seconds,
                return_embedding=return_embedding,
            )
            _record(AUDIO_SPOOFING_ANALYSIS_TFCL, result, "Inferindo TFCL XLS-R…")

    if not individual_results:
        if unavailable:
            raise RuntimeError(
                "Nenhum detector selecionado produziu resultado. Indisponiveis: "
                + "; ".join(unavailable)
            )
        raise RuntimeError("Nenhum detector de spoofing produziu resultado")

    report_progress(on_progress, 78, "Agregando escores dos detectores…")

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
        "decision": primary.get("decision"),
        "window_count": primary.get("window_count", 0),
    }
