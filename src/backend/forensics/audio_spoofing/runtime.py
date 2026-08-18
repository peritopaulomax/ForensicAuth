"""Runtime probes for multi-detector audio spoofing."""

from __future__ import annotations

from typing import Tuple

from forensics.df_arena import df_arena_pipeline as df_arena
from forensics.sls_spoofing import sls_runtime
from forensics.tfcl_spoofing import tfcl_runtime
from forensics.wedefense_spoofing import wedefense_runtime


AUDIO_SPOOFING_ANALYSIS_DF_ARENA = "df_arena_1b"
AUDIO_SPOOFING_ANALYSIS_SLS_XLSR = "sls_xlsr"
AUDIO_SPOOFING_ANALYSIS_WEDEFENSE = "wedefense_wavlm_mhfa"
AUDIO_SPOOFING_ANALYSIS_TFCL = "tfcl_xlsr"

# Full registry (API ainda aceita se selected_analyses forçar ids ocultos).
REGISTERED_AUDIO_SPOOFING_ANALYSES = (
    AUDIO_SPOOFING_ANALYSIS_DF_ARENA,
    AUDIO_SPOOFING_ANALYSIS_SLS_XLSR,
    AUDIO_SPOOFING_ANALYSIS_WEDEFENSE,
    AUDIO_SPOOFING_ANALYSIS_TFCL,
)
# UI / default de job: apenas estes aparecem e sao pre-selecionados.
UI_VISIBLE_AUDIO_SPOOFING_ANALYSES = (
    AUDIO_SPOOFING_ANALYSIS_DF_ARENA,
    AUDIO_SPOOFING_ANALYSIS_WEDEFENSE,
)
DEFAULT_AUDIO_SPOOFING_ANALYSES = UI_VISIBLE_AUDIO_SPOOFING_ANALYSES
VALID_AUDIO_SPOOFING_ANALYSES = set(REGISTERED_AUDIO_SPOOFING_ANALYSES)

DETECTOR_DISPLAY = {
    AUDIO_SPOOFING_ANALYSIS_DF_ARENA: "DF Arena 1B",
    AUDIO_SPOOFING_ANALYSIS_SLS_XLSR: "SLS XLS-R (ACM MM 2024)",
    AUDIO_SPOOFING_ANALYSIS_WEDEFENSE: "WeDefense ASV2025 WavLM + MHFA",
    AUDIO_SPOOFING_ANALYSIS_TFCL: "TFCL XLS-R (ACM MM 2026)",
}

DETECTOR_CATALOG = [
    {
        "id": AUDIO_SPOOFING_ANALYSIS_DF_ARENA,
        "label": DETECTOR_DISPLAY[AUDIO_SPOOFING_ANALYSIS_DF_ARENA],
        "ui_visible": True,
        "description": (
            "Modelo universal antispoofing do Speech DF Arena, treinado em ASVspoof, "
            "CodecFake, SONAR e outros benchmarks. Janelas de 4 s @ 16 kHz."
        ),
        "paper_title": "Speech DF Arena: A Leaderboard for Speech DeepFake Detection Models",
        "paper_url": "https://arxiv.org/abs/2509.02859",
        "repo_url": "https://huggingface.co/Speech-Arena-2025/DF_Arena_1B_V_1",
    },
    {
        "id": AUDIO_SPOOFING_ANALYSIS_SLS_XLSR,
        "label": DETECTOR_DISPLAY[AUDIO_SPOOFING_ANALYSIS_SLS_XLSR],
        "ui_visible": False,
        "description": (
            "XLS-R 300M auto-supervisionado + classificador SLS (ACM MM 2024). "
            "Log-softmax idx0=spoof, idx1=bonafide."
        ),
        "paper_title": "Audio Deepfake Detection with Self-Supervised XLS-R and SLS Classifier",
        "paper_url": "https://doi.org/10.1145/3664647.3681345",
        "repo_url": "https://github.com/QiShanZhang/SLSforASVspoof-2021-DF",
    },
    {
        "id": AUDIO_SPOOFING_ANALYSIS_WEDEFENSE,
        "label": DETECTOR_DISPLAY[AUDIO_SPOOFING_ANALYSIS_WEDEFENSE],
        "ui_visible": True,
        "description": (
            "WavLM Base podado + MHFA (ASVspoof 2025). "
            "Logits idx0=bonafide, idx1=spoof — mapeados para convencao VA Suite."
        ),
        "paper_title": "WeDefense: A Toolkit to Defend Against Fake Audio",
        "paper_url": "https://arxiv.org/abs/2601.15240",
        "repo_url": "https://huggingface.co/JYP2024/Wedefense_ASV2025_WavLM_Base_Pruning",
    },
    {
        "id": AUDIO_SPOOFING_ANALYSIS_TFCL,
        "label": DETECTOR_DISPLAY[AUDIO_SPOOFING_ANALYSIS_TFCL],
        "ui_visible": False,
        "description": (
            "Time-Frequency Consistency Learning (TFCL): XLS-R 300M + AASIST com "
            "aprendizado de consistencia tempo-frequencia sob distorcoes AFE. "
            "Janelas ~4,04 s (64600 amostras @ 16 kHz)."
        ),
        "paper_title": "Time-Frequency Consistency Learning for Robust Speech Deepfake Detection",
        "paper_url": "https://github.com/JunXue-tech/TFCL",
        "repo_url": "https://huggingface.co/datasets/JunXueTech/TFCL",
    },
]


def runtime_status() -> Tuple[bool, str]:
    """At least one detector must be available for the technique to run."""
    df_ok, df_reason = df_arena.runtime_status()
    sls_ok, sls_reason = sls_runtime.runtime_status()
    wd_ok, wd_reason = wedefense_runtime.runtime_status()
    tfcl_ok, tfcl_reason = tfcl_runtime.runtime_status()
    if df_ok or sls_ok or wd_ok or tfcl_ok:
        return True, ""
    return False, (
        f"Nenhum detector disponivel (DF Arena: {df_reason}; "
        f"SLS: {sls_reason}; WeDefense: {wd_reason}; TFCL: {tfcl_reason})"
    )


def detector_runtime_status(detector_id: str) -> Tuple[bool, str]:
    if detector_id == AUDIO_SPOOFING_ANALYSIS_DF_ARENA:
        return df_arena.runtime_status()
    if detector_id == AUDIO_SPOOFING_ANALYSIS_SLS_XLSR:
        return sls_runtime.runtime_status()
    if detector_id == AUDIO_SPOOFING_ANALYSIS_WEDEFENSE:
        return wedefense_runtime.runtime_status()
    if detector_id == AUDIO_SPOOFING_ANALYSIS_TFCL:
        return tfcl_runtime.runtime_status()
    return False, f"Detector desconhecido: {detector_id}"
