"""Runtime probes for multi-detector audio spoofing."""

from __future__ import annotations

from typing import Tuple

from core.legacy.df_arena import df_arena_pipeline as df_arena
from core.legacy.sls_spoofing import sls_runtime
from core.legacy.wedefense_spoofing import wedefense_runtime


def runtime_status() -> Tuple[bool, str]:
    """At least one detector must be available for the technique to run."""
    df_ok, df_reason = df_arena.runtime_status()
    sls_ok, sls_reason = sls_runtime.runtime_status()
    wd_ok, wd_reason = wedefense_runtime.runtime_status()
    if df_ok or sls_ok or wd_ok:
        return True, ""
    return False, (
        f"Nenhum detector disponivel (DF Arena: {df_reason}; "
        f"SLS: {sls_reason}; WeDefense: {wd_reason})"
    )


def detector_runtime_status(detector_id: str) -> Tuple[bool, str]:
    if detector_id == AUDIO_SPOOFING_ANALYSIS_DF_ARENA:
        return df_arena.runtime_status()
    if detector_id == AUDIO_SPOOFING_ANALYSIS_SLS_XLSR:
        return sls_runtime.runtime_status()
    if detector_id == AUDIO_SPOOFING_ANALYSIS_WEDEFENSE:
        return wedefense_runtime.runtime_status()
    return False, f"Detector desconhecido: {detector_id}"


AUDIO_SPOOFING_ANALYSIS_DF_ARENA = "df_arena_1b"
AUDIO_SPOOFING_ANALYSIS_SLS_XLSR = "sls_xlsr"
AUDIO_SPOOFING_ANALYSIS_WEDEFENSE = "wedefense_wavlm_mhfa"

DEFAULT_AUDIO_SPOOFING_ANALYSES = (
    AUDIO_SPOOFING_ANALYSIS_DF_ARENA,
    AUDIO_SPOOFING_ANALYSIS_SLS_XLSR,
    AUDIO_SPOOFING_ANALYSIS_WEDEFENSE,
)
VALID_AUDIO_SPOOFING_ANALYSES = set(DEFAULT_AUDIO_SPOOFING_ANALYSES)

DETECTOR_DISPLAY = {
    AUDIO_SPOOFING_ANALYSIS_DF_ARENA: "DF Arena 1B",
    AUDIO_SPOOFING_ANALYSIS_SLS_XLSR: "SLS XLS-R (ACM MM 2024)",
    AUDIO_SPOOFING_ANALYSIS_WEDEFENSE: "WeDefense ASV2025 WavLM + MHFA",
}

DETECTOR_CATALOG = [
    {
        "id": AUDIO_SPOOFING_ANALYSIS_DF_ARENA,
        "label": DETECTOR_DISPLAY[AUDIO_SPOOFING_ANALYSIS_DF_ARENA],
        "paper": "Speech-Arena-2025/DF_Arena_1B",
    },
    {
        "id": AUDIO_SPOOFING_ANALYSIS_SLS_XLSR,
        "label": DETECTOR_DISPLAY[AUDIO_SPOOFING_ANALYSIS_SLS_XLSR],
        "paper": "Audio Deepfake Detection with Self-supervised XLS-R and SLS classifier",
    },
    {
        "id": AUDIO_SPOOFING_ANALYSIS_WEDEFENSE,
        "label": DETECTOR_DISPLAY[AUDIO_SPOOFING_ANALYSIS_WEDEFENSE],
        "paper": "JYP2024/Wedefense_ASV2025_WavLM_Base_Pruning",
    },
]
