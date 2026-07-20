"""Reference-population LR calibration for audio spoofing detection.

Mirrors synthetic_lr_reference.py for the three active spoofing detectors:
DF Arena 1B, SLS XLS-R, WeDefense WavLM+MHFA.

Positive LR favors H1 = bonafide (authentic speech).
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from core.legacy.audio_spoofing.runtime import (
    AUDIO_SPOOFING_ANALYSIS_DF_ARENA,
    AUDIO_SPOOFING_ANALYSIS_SLS_XLSR,
    AUDIO_SPOOFING_ANALYSIS_WEDEFENSE,
    DEFAULT_AUDIO_SPOOFING_ANALYSES,
)
from core.progress import ProgressCallback, report_progress
from sklearn.metrics import roc_curve

from core.latent_typicality.config import (
    DEFAULT_DISTANCE as TYPICALITY_DISTANCE,
    DEFAULT_K as TYPICALITY_K,
    DEFAULT_SYSTEM as TYPICALITY_SYSTEM,
    DEFAULT_TYPICALITY_EPS,
)
from core.latent_typicality.features import feature_columns_for_detectors, build_system_features_for_detectors
from core.latent_typicality.representations_utils import (
    ORIGINAL_AUGMENTATION_TAG,
    build_sample_id,
    load_embeddings_row,
    representations_matrix_available,
    row_has_embeddings,
)
from core.latent_typicality.typicality import TypicalityReference, build_typicality_reference
from core.synthetic_lr_reference import (
    DEFAULT_META_CLASSIFIER,
    META_CLASSIFIERS,
    _apply,
    _cache_dir,
    _classifier_feature_importance,
    _classifier_label,
    _fit_bigauss,
    _load_lr_cache,
    _metrics,
    _plot_distribution,
    _plot_identity,
    _plot_tippett,
    _save_lr_cache,
    _score_dataframe,
    _score_matrix_hash,
    _serialize_calibration,
    _train_meta_classifier,
    _validate_classifier,
    _write_json,
)

ALL_DETECTORS = DEFAULT_AUDIO_SPOOFING_ANALYSES
FEATURE_SUFFIX = "_bonafide_logit"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCORE_MATRIX = PROJECT_ROOT / "outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full.csv"
DEFAULT_AUGMENTED_SCORE_MATRIX = (
    PROJECT_ROOT / "outputs/lr_calibration/audio_spoofing/score_matrices/lr_scores_balanced_full_augmented.csv"
)
DEFAULT_REPRESENTATIONS_MATRIX = (
    PROJECT_ROOT / "outputs/lr_calibration/audio_spoofing/representations/representations.csv"
)
AUGMENTATION_NAMES: tuple[str, ...] = ("mp3_128k", "opus_32k", "noise_snr_20", "noise_snr_15")
AUGMENTATION_MULTIPLIER = 1 + len(AUGMENTATION_NAMES)
# Cap paralelismo na materializacao k-NN (SSD + varios usuarios concorrentes).
TYPICALITY_MATERIALIZE_JOBS = min(
    12,
    max(1, int(os.getenv("VA_LR_TYPICALITY_JOBS", "8"))),
)
# Materialize typicality in row chunks so np.stack never loads the full split at once.
# Default 512: low overhead on 64–128 GB hosts; lower via VA_LR_TYPICALITY_BATCH if OOM.
TYPICALITY_MATERIALIZE_BATCH = max(32, int(os.getenv("VA_LR_TYPICALITY_BATCH", "512")))
SAMPLE_PER_CLASS = 500
TRAIN_PER_CLASS = 250
CALIB_PER_CLASS = 125
TEST_PER_CLASS = 125

BASE_LABELS: dict[str, str] = {
    "ASVspoof2019_LA": "ASVspoof 2019 LA",
    "ASVspoof2021_LA_eval": "ASVspoof 2021 LA eval",
    "ASVspoof5": "ASVspoof 5",
    "CodecFake": "CodecFake",
    "ADD2022": "ADD 2022",
    "ADD2023": "ADD 2023",
    "DFADD": "DFADD",
    "SONAR": "SONAR",
    "In-The-Wild": "In-The-Wild",
    "Fake-or-Real": "Fake-or-Real",
    "LibriSeVoc": "LibriSeVoc",
}

BASE_CATALOG: dict[str, dict[str, str]] = {
    "ASVspoof2019_LA": {
        "description": (
            "Logical access ASVspoof 2019 — TTS/VC clássico sobre VCTK; split flac_E "
            "para avaliação de countermeasures."
        ),
        "paper_title": "ASVspoof 2019: Future Horizons in Spoofed and Countermeasure Speech",
        "paper_url": "https://www.asvspoof.org/",
    },
    "ASVspoof2021_LA_eval": {
        "description": (
            "ASVspoof 2021 LA evaluation — ataques neural TTS/VC; referência histórica "
            "para generalização cross-algoritmo."
        ),
        "paper_title": "ASVspoof 2021: automatic speaker verification spoofing and countermeasures",
        "paper_url": "https://www.asvspoof.org/",
    },
    "ASVspoof5": {
        "description": (
            "ASVspoof 5 evaluation (flac_E_eval) — deepfakes recentes e condições "
            "de canal ampliadas."
        ),
        "paper_title": "ASVspoof 5: Design, Collection and Validation of Spoofing and Deepfake Speech",
        "paper_url": "https://www.asvspoof.org/",
    },
    "CodecFake": {
        "description": (
            "CodecFake — spoofing sob diferentes condições de codec neural (C1–C7); "
            "fala re-sintetizada via codecs SOTA."
        ),
        "paper_title": "CodecFake: Enhancing Anti-Spoofing Models Against Deepfake Audios from Codec-Based Speech Synthesis Systems",
        "paper_url": "https://arxiv.org/abs/2406.07237",
    },
    "ADD2022": {
        "description": (
            "Audio Deepfake Detection 2022 — tracks 1 (TTS) e 32 (VC) no split de teste."
        ),
        "paper_title": "ADD 2022 Challenge: Audio Deepfake Detection",
        "paper_url": "https://www.addchallenge.org/add2022",
    },
    "ADD2023": {
        "description": (
            "Audio Deepfake Detection 2023 — tracks de teste com ataques TTS/VC recentes."
        ),
        "paper_title": "ADD 2023 Challenge: Audio Deepfake Detection",
        "paper_url": "https://www.addchallenge.org/add2023",
    },
    "DFADD": {
        "description": (
            "Deepfake ADD — geradores nomeados no arquivo (GradTTS, FastSpeech2, etc.) "
            "no split test_converted2."
        ),
        "paper_title": "DFADD: Deepfake Audio Detection Dataset",
        "paper_url": "https://github.com/Speech-Arena/speech_df_arena",
    },
    "SONAR": {
        "description": (
            "SONAR — múltiplos geradores TTS/neural (PromptTTS2, VALL-E, VoiceBox, etc.) "
            "para avaliação cross-generator."
        ),
        "paper_title": "SONAR: A Synthetic Speech Detection Benchmark",
        "paper_url": "https://github.com/Speech-Arena/speech_df_arena",
    },
    "In-The-Wild": {
        "description": (
            "Áudio in-the-wild (YouTube, podcasts) — condições acústicas e de canal "
            "menos controladas."
        ),
        "paper_title": "In-The-Wild Spoofing Attack Detection",
        "paper_url": "https://arxiv.org/abs/2207.01559",
    },
    "Fake-or-Real": {
        "description": (
            "Fake-or-Real — pares bonafide/spoof balanceados para detecção geral."
        ),
        "paper_title": "Fake-or-Real: A Benchmark for Audio Deepfake Detection",
        "paper_url": "https://github.com/Speech-Arena/speech_df_arena",
    },
    "LibriSeVoc": {
        "description": (
            "LibriSeVoc — spoofing baseado em vocoders (WaveNet, WaveGrad, MelGAN, etc.) "
            "sobre LibriSpeech."
        ),
        "paper_title": "LibriSeVoc: A Vocoder-based Spoofing Dataset",
        "paper_url": "https://github.com/Speech-Arena/speech_df_arena",
    },
}

REFERENCE_GENERATORS: dict[str, list[str]] = {
    "ASVspoof2019_LA": ["flac_E"],
    "ASVspoof2021_LA_eval": ["LA_eval"],
    "ASVspoof5": ["flac_E_eval"],
    "CodecFake": ["C1", "C2", "C3", "C4", "C5", "C6", "C7"],
    "ADD2022": ["track1test", "track32test"],
    "ADD2023": ["Track1.2_testR1", "Track1.2_testR2"],
    "DFADD": ["GradTTS", "NaturalSpeech2", "StyleTTS2", "matcha", "pflow"],
    "SONAR": [
        "PromptTTS2",
        "FlashSpeech",
        "VALLE",
        "VoiceBox",
        "xTTS",
        "AudioGen",
        "NaturalSpeech3",
        "OpenAI_fixed",
    ],
    "In-The-Wild": ["In-The-Wild"],
    "Fake-or-Real": ["Fake-or-Real"],
    "LibriSeVoc": [
        "parallel_wave_gan",
        "melgan",
        "wavernn",
        "diffwave",
        "wavenet",
        "wavegrad",
    ],
}

CODEC_CONDITION_LABELS: dict[str, str] = {
    "C1": "Codec neural C1 (SoundStorm)",
    "C2": "Codec neural C2",
    "C3": "Codec neural C3",
    "C4": "Codec neural C4",
    "C5": "Codec neural C5",
    "C6": "Codec neural C6",
    "C7": "Codec neural C7",
}

@dataclass(frozen=True)
class PopulationItem:
    base_group: str
    subgroup: str

    @property
    def key(self) -> str:
        return f"{self.base_group}/{self.subgroup}"


FIT_REFERENCE_SPLITS: frozenset[str] = frozenset({"train_logreg", "calibration_bigauss"})
TEST_REFERENCE_SPLIT = "test_bigauss"


@dataclass(frozen=True)
class ReferenceSelectionRoles:
    """Separate subgroups for meta-classifier fit/calibration vs held-out test."""

    fit_items: tuple[PopulationItem, ...]
    test_items: tuple[PopulationItem, ...]

    @property
    def union_items(self) -> tuple[PopulationItem, ...]:
        by_key: dict[str, PopulationItem] = {}
        for item in (*self.fit_items, *self.test_items):
            by_key[item.key] = item
        return tuple(by_key.values())

    @property
    def fit_keys(self) -> frozenset[str]:
        return frozenset(item.key for item in self.fit_items)

    @property
    def test_keys(self) -> frozenset[str]:
        return frozenset(item.key for item in self.test_items)


# Cadeia forense típica: clonagem comercial (ElevenLabs e similares) + mix LA recente + distribuição in-the-wild.
# CodecFake (C1–C7) fica no catálogo, mas fora do default: modela codec neural na síntese, não Opus/MP3 pós-envio.
DEFAULT_VOICE_CLONE_REFERENCE: tuple[PopulationItem, ...] = (
    PopulationItem("DFADD", "StyleTTS2"),
    PopulationItem("DFADD", "NaturalSpeech2"),
    PopulationItem("SONAR", "xTTS"),
    PopulationItem("SONAR", "PromptTTS2"),
    PopulationItem("SONAR", "VoiceBox"),
    PopulationItem("ASVspoof5", "flac_E_eval"),
    PopulationItem("In-The-Wild", "In-The-Wild"),
)


def default_reference_population() -> list[dict[str, str]]:
    return [{"base_group": item.base_group, "subgroup": item.subgroup} for item in DEFAULT_VOICE_CLONE_REFERENCE]


DETECTOR_PAPERS: dict[str, dict[str, str]] = {
    AUDIO_SPOOFING_ANALYSIS_DF_ARENA: {
        "label": "DF Arena 1B",
        "description": (
            "Modelo universal antispoofing do Speech DF Arena, treinado em ASVspoof, "
            "CodecFake, SONAR e outros benchmarks."
        ),
        "paper_title": "Speech DF Arena: A Leaderboard for Speech DeepFake Detection Models",
        "paper_url": "https://arxiv.org/abs/2509.02859",
        "repo_url": "https://huggingface.co/Speech-Arena-2025/DF_Arena_1B_V_1",
    },
    AUDIO_SPOOFING_ANALYSIS_SLS_XLSR: {
        "label": "SLS XLS-R (ACM MM 2024)",
        "description": (
            "XLS-R 300M com classificador Sensitive Layer Selection (SLS) sobre "
            "as 24 camadas do transformer."
        ),
        "paper_title": "Audio Deepfake Detection with Self-Supervised XLS-R and SLS Classifier",
        "paper_url": "https://doi.org/10.1145/3664647.3681345",
        "repo_url": "https://github.com/QiShanZhang/SLSforASVspoof-2021-DF",
    },
    AUDIO_SPOOFING_ANALYSIS_WEDEFENSE: {
        "label": "WeDefense ASV2025 WavLM + MHFA",
        "description": (
            "WavLM Base podado com MHFA para detecção de spoofing; checkpoint ASVspoof 2025."
        ),
        "paper_title": "WeDefense: WavLM Base Pruning for Anti-Spoofing (ASVspoof 2025)",
        "paper_url": "https://huggingface.co/JYP2024/Wedefense_ASV2025_WavLM_Base_Pruning",
        "repo_url": "https://huggingface.co/JYP2024/Wedefense_ASV2025_WavLM_Base_Pruning",
    },
}

def _macro_items_for_generators() -> list[PopulationItem]:
    items: list[PopulationItem] = []
    for base, generators in REFERENCE_GENERATORS.items():
        for generator in generators:
            items.append(PopulationItem(base, generator))
    return items


REFERENCE_MACRO_CATEGORIES: dict[str, dict[str, Any]] = {
    "asv_classic": {
        "label": "ASVspoof (LA)",
        "year_range": "2019–2025",
        "description": "Competições ASVspoof logical access — referência histórica de countermeasures.",
        "items": [
            PopulationItem("ASVspoof2019_LA", "flac_E"),
            PopulationItem("ASVspoof2021_LA_eval", "LA_eval"),
            PopulationItem("ASVspoof5", "flac_E_eval"),
        ],
    },
    "codec_conditions": {
        "label": "CodecFake (7 codecs neurais)",
        "year_range": "2024",
        "description": (
            "C1–C7 são condições de codec neural distintas (SoundStorm, etc.), "
            "não geradores TTS — spoofing via re-síntese codec."
        ),
        "items": [PopulationItem("CodecFake", code) for code in REFERENCE_GENERATORS["CodecFake"]],
    },
    "deepfake_challenges": {
        "label": "Desafios deepfake (ADD / DFADD / SONAR)",
        "year_range": "2022–2024",
        "description": "Competições ADD, geradores nomeados em DFADD e TTS do benchmark SONAR.",
        "items": [
            PopulationItem("ADD2022", "track1test"),
            PopulationItem("ADD2022", "track32test"),
            PopulationItem("ADD2023", "Track1.2_testR1"),
            PopulationItem("ADD2023", "Track1.2_testR2"),
            *[PopulationItem("DFADD", g) for g in REFERENCE_GENERATORS["DFADD"]],
            *[PopulationItem("SONAR", g) for g in REFERENCE_GENERATORS["SONAR"]],
        ],
    },
    "in_the_wild": {
        "label": "In-the-wild / vocoder / misc",
        "year_range": "2020–2024",
        "description": "In-the-wild, Fake-or-Real e vocoders LibriSeVoc (bonafide compartilhado via gt).",
        "items": [
            PopulationItem("In-The-Wild", "In-The-Wild"),
            PopulationItem("Fake-or-Real", "Fake-or-Real"),
            *[PopulationItem("LibriSeVoc", g) for g in REFERENCE_GENERATORS["LibriSeVoc"]],
        ],
    },
}


def _base_catalog_entry(base_id: str) -> dict[str, str | None]:
    meta = BASE_CATALOG.get(base_id, {})
    return {
        "description": meta.get("description", ""),
        "paper_title": meta.get("paper_title") or None,
        "paper_url": meta.get("paper_url") or None,
    }


def _feature_cols(selected_detectors: tuple[str, ...]) -> list[str]:
    return [f"{detector}{FEATURE_SUFFIX}" for detector in selected_detectors]


def _eer_spoof_detector(df: pd.DataFrame, detector_id: str) -> float | None:
    """EER (%) for a single detector using spoof_prob; positive class = spoof."""
    col = f"{detector_id}_spoof_prob"
    if col not in df.columns:
        return None
    scores = pd.to_numeric(df[col], errors="coerce")
    mask = scores.notna() & np.isfinite(scores)
    if not mask.any():
        return None
    y = df.loc[mask, "y_fake"].astype(int).to_numpy()
    s = scores.loc[mask].to_numpy(dtype=float)
    if len(set(y.tolist())) < 2:
        return None
    fpr, tpr, _ = roc_curve(y, s)
    fnr = 1.0 - tpr
    idx = int(np.nanargmin(np.abs(fnr - fpr)))
    eer = float((fpr[idx] + fnr[idx]) / 2.0)
    return round(eer * 100.0, 2)


def build_generator_detector_eers(score_matrix: Path | None = None) -> dict[str, list[float | None]]:
    """Map ``dataset/generator`` keys to [DF Arena, SLS, WeDefense] EER percent values."""
    path = score_matrix or DEFAULT_SCORE_MATRIX
    if not path.is_file():
        return {}
    df = _load_scores(path)
    out: dict[str, list[float | None]] = {}
    for dataset, generators in REFERENCE_GENERATORS.items():
        for generator in generators:
            key = f"{dataset}/{generator}"
            sub = df[
                df["dataset"].astype(str).eq(dataset) & df["generator"].astype(str).eq(generator)
            ]
            out[key] = [_eer_spoof_detector(sub, detector) for detector in ALL_DETECTORS]
    return out


def detector_eer_catalog_metadata() -> dict[str, Any]:
    return {
        "detector_eer_order": list(ALL_DETECTORS),
        "detector_eer_labels": [DETECTOR_PAPERS[detector]["label"] for detector in ALL_DETECTORS],
        "default_reference_items": default_reference_population(),
    }


def reference_macro_catalog(*, score_matrix: Path | None = None) -> list[dict[str, Any]]:
    generator_eers = build_generator_detector_eers(score_matrix)
    catalog: list[dict[str, Any]] = []
    for macro_id, macro in REFERENCE_MACRO_CATEGORIES.items():
        bases: dict[str, dict[str, Any]] = {}
        for item in macro["items"]:
            base = bases.setdefault(
                item.base_group,
                {
                    "id": item.base_group,
                    "label": BASE_LABELS.get(item.base_group, item.base_group),
                    "generators": [],
                    **_base_catalog_entry(item.base_group),
                },
            )
            label = (
                CODEC_CONDITION_LABELS.get(item.subgroup, item.subgroup)
                if item.base_group == "CodecFake"
                else item.subgroup
            )
            base["generators"].append(
                {
                    "id": item.subgroup,
                    "label": label,
                    "deploy_year": None,
                    "detector_eer_percent": generator_eers.get(item.key),
                }
            )
        catalog.append(
            {
                "id": macro_id,
                "label": macro["label"],
                "year_range": macro["year_range"],
                "description": macro["description"],
                "bases": list(bases.values()),
            }
        )
    return catalog


def detector_papers_catalog() -> list[dict[str, str]]:
    return [{"id": detector_id, **meta} for detector_id, meta in DETECTOR_PAPERS.items()]


def normalize_reference_selection(selection: Any) -> list[PopulationItem]:
    if selection is None:
        return list(DEFAULT_VOICE_CLONE_REFERENCE)
    if isinstance(selection, str):
        if selection.startswith("macro:"):
            macro = REFERENCE_MACRO_CATEGORIES.get(selection[len("macro:"):])
            if macro:
                return list(macro["items"])
        if "/" in selection:
            base, subgroup = selection.split("/", 1)
            return [PopulationItem(base.strip(), subgroup.strip())]
        generators = REFERENCE_GENERATORS.get(selection.strip())
        if generators:
            return [PopulationItem(selection.strip(), generator) for generator in generators]
        return [PopulationItem(selection.strip(), selection.strip())]
    if isinstance(selection, dict):
        macro_id = str(selection.get("macro") or "")
        if macro_id:
            macro = REFERENCE_MACRO_CATEGORIES.get(macro_id)
            if macro:
                return list(macro["items"])
        items = selection.get("items") or selection.get("generators") or []
        return normalize_reference_selection(items)
    if isinstance(selection, (list, tuple)):
        out: list[PopulationItem] = []
        for item in selection:
            if isinstance(item, PopulationItem):
                out.append(item)
            elif isinstance(item, dict):
                out.append(
                    PopulationItem(
                        str(item.get("base_group") or item.get("base") or ""),
                        str(item.get("subgroup") or item.get("generator") or ""),
                    )
                )
            elif isinstance(item, str):
                out.extend(normalize_reference_selection(item))
            else:
                raise ValueError(f"Seleção inválida: {item!r}")
        return out
    raise ValueError(f"Seleção inválida: {selection!r}")


def normalize_reference_selection_roles(selection: Any) -> ReferenceSelectionRoles:
    """Parse fit/test subgroup selections with backward-compatible ``items`` fallback."""
    if selection is None:
        items = tuple(DEFAULT_VOICE_CLONE_REFERENCE)
        return ReferenceSelectionRoles(items, items)

    if isinstance(selection, dict):
        fit_raw = selection.get("fit_items")
        test_raw = selection.get("test_items")
        if fit_raw is not None or test_raw is not None:
            fit_items = tuple(normalize_reference_selection(fit_raw or []))
            test_items = tuple(normalize_reference_selection(test_raw or []))
            if not fit_items:
                raise ValueError("fit_items nao pode ser vazio para calibracao LR.")
            if not test_items:
                test_items = fit_items
            return ReferenceSelectionRoles(fit_items, test_items)
        items = tuple(normalize_reference_selection(selection))
        return ReferenceSelectionRoles(items, items)

    items = tuple(normalize_reference_selection(selection))
    return ReferenceSelectionRoles(items, items)


def _filter_working_split(split: pd.DataFrame, roles: ReferenceSelectionRoles) -> pd.DataFrame:
    """Keep only rows used in this experiment: fit splits 1+2 and test split 3."""
    keys = split["reference_key"].astype(str)
    fit_mask = keys.isin(roles.fit_keys) & split["reference_split"].astype(str).isin(FIT_REFERENCE_SPLITS)
    test_mask = keys.isin(roles.test_keys) & split["reference_split"].astype(str).eq(TEST_REFERENCE_SPLIT)
    return split.loc[fit_mask | test_mask].copy()


def _normalize_generators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "generator" not in df.columns:
        df["generator"] = ""
    df["generator"] = df["generator"].fillna("").astype(str).str.strip()
    if "subset" in df.columns:
        subset = df["subset"].fillna("").astype(str).str.strip()
        empty = df["generator"].eq("")
        df.loc[empty, "generator"] = subset[empty]
    still_empty = df["generator"].eq("")
    if "dataset" in df.columns:
        df.loc[still_empty, "generator"] = df.loc[still_empty, "dataset"].astype(str)
    return df


def _load_scores(score_matrix: Path) -> pd.DataFrame:
    df = pd.read_csv(score_matrix, low_memory=False)
    if "error" in df.columns:
        df = df[df["error"].fillna("").eq("")].copy()
    df = _normalize_generators(df)
    if "y_spoof" in df.columns:
        df["y_fake"] = df["y_spoof"].astype(int)
    elif "label" in df.columns:
        df["y_fake"] = (df["label"].astype(str).str.lower() == "spoof").astype(int)
    else:
        raise RuntimeError("Score matrix deve conter y_spoof ou label.")
    for detector in ALL_DETECTORS:
        col = f"{detector}{FEATURE_SUFFIX}"
        prob_col = f"{detector}_bonafide_prob"
        if col not in df.columns and prob_col in df.columns:
            eps = 1e-6
            values = pd.to_numeric(df[prob_col], errors="coerce").clip(eps, 1.0 - eps)
            df[col] = np.log(values / (1.0 - values))
    split_map = {
        "calibration_train": "train_logreg",
        "calibration_bigauss": "calibration_bigauss",
        "evaluation": "test_bigauss",
    }
    if "purpose" in df.columns:
        df["reference_split"] = df["purpose"].map(split_map).fillna(df.get("reference_split", df["purpose"]))
    elif "reference_split" in df.columns:
        df["reference_split"] = df["reference_split"].map(split_map).fillna(df["reference_split"])
    if "augmentation" not in df.columns:
        df["augmentation"] = ""
    else:
        df["augmentation"] = df["augmentation"].fillna("").astype(str)
    return df


def _filter_rows_with_embeddings(df: pd.DataFrame) -> pd.DataFrame:
    """Drop representation rows whose embedding .npy files are missing on disk."""
    if df.empty:
        return df
    required = [f"{detector}_embedding_path" for detector in ALL_DETECTORS]
    if not all(col in df.columns for col in required):
        return df
    mask = df.apply(row_has_embeddings, axis=1)
    dropped = int((~mask).sum())
    if dropped:
        import logging

        logging.getLogger(__name__).warning(
            "Ignorando %d linhas da matriz de representacoes sem embeddings 3/3 no disco",
            dropped,
        )
    return df.loc[mask].copy()


def _filter_rows_with_finite_features(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """Drop rows with NaN/non-finite values in the meta-classifier feature columns."""
    if df.empty:
        return df
    present = [col for col in feature_cols if col in df.columns]
    if not present:
        return df
    values = df[present].apply(pd.to_numeric, errors="coerce")
    mask = np.isfinite(values.to_numpy(dtype=float)).all(axis=1)
    dropped = int((~mask).sum())
    if dropped:
        import logging

        logging.getLogger(__name__).warning(
            "Ignorando %d linhas da score matrix com logits nao-finitos (NaN) nas features",
            dropped,
        )
    return df.loc[mask].copy()


def _query_for_item(df: pd.DataFrame, item: PopulationItem, y_fake: int) -> pd.Series:
    label = "spoof" if y_fake else "bonafide"
    query = df["dataset"].astype(str).eq(item.base_group) & df["generator"].astype(str).eq(item.subgroup)
    if "label" in df.columns:
        query &= df["label"].astype(str).str.lower().eq(label)
    else:
        query &= df["y_fake"].eq(y_fake)
    return query


def _augmentation_strata(df: pd.DataFrame) -> pd.Series:
    if "augmentation" in df.columns:
        return df["augmentation"].fillna("").astype(str)
    return pd.Series("", index=df.index)


def _sample_stratified(
    candidates: pd.DataFrame,
    n_total: int,
    rng: np.random.Generator,
    context: str,
) -> pd.DataFrame:
    if candidates.empty:
        if n_total == 0:
            return candidates.copy()
        raise RuntimeError(f"{context}: nenhum candidato disponivel")

    strata = _augmentation_strata(candidates)
    unique_strata = sorted(strata.unique())
    n_strata = len(unique_strata)
    base = n_total // n_strata
    remainder = n_total % n_strata

    sampled: list[pd.DataFrame] = []
    for idx, stratum in enumerate(unique_strata):
        stratum_df = candidates[strata == stratum]
        n = base + (1 if idx < remainder else 0)
        if len(stratum_df) >= n:
            sampled.append(
                stratum_df.sample(n=n, random_state=int(rng.integers(0, 2**31 - 1))).copy()
            )
        else:
            sampled.append(
                stratum_df.sample(n=n, replace=True, random_state=int(rng.integers(0, 2**31 - 1))).copy()
            )
    return pd.concat(sampled, ignore_index=True)


def _sample_with_fallback(
    candidates: pd.DataFrame,
    n: int,
    rng: np.random.Generator,
    context: str,
) -> pd.DataFrame:
    if "augmentation" in candidates.columns and candidates["augmentation"].fillna("").astype(str).nunique() > 1:
        return _sample_stratified(candidates, n, rng, context)
    if len(candidates) >= n:
        return candidates.sample(n=n, random_state=int(rng.integers(0, 2**31 - 1))).copy()
    return candidates.sample(n=n, replace=True, random_state=int(rng.integers(0, 2**31 - 1))).copy()


def _build_reference_sample(
    df: pd.DataFrame,
    items: list[PopulationItem],
    seed: int,
    sample_multiplier: int = 1,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    sample_per_class = SAMPLE_PER_CLASS * max(1, sample_multiplier)
    frames: list[pd.DataFrame] = []
    for item in items:
        for y_fake in (0, 1):
            candidates = df[_query_for_item(df, item, y_fake)]
            sampled = _sample_with_fallback(
                candidates,
                sample_per_class,
                rng,
                f"{item.key}/y_fake={y_fake}",
            )
            sampled = sampled.copy()
            sampled["reference_base_group"] = item.base_group
            sampled["reference_subgroup"] = item.subgroup
            sampled["reference_key"] = item.key
            frames.append(sampled)
    return pd.concat(frames, ignore_index=True)


def _filter_matrix_scope(df: pd.DataFrame, *, augmented_reference: bool) -> pd.DataFrame:
    if "augmentation" not in df.columns:
        return df.copy()
    aug = df["augmentation"].fillna("").astype(str)
    if augmented_reference:
        return df.copy()
    return df[aug.isin(("", ORIGINAL_AUGMENTATION_TAG))].copy()


def _parallel_load_embeddings(paths: list[str]) -> list[np.ndarray]:
    from joblib import Parallel, delayed

    if not paths:
        return []
    if len(paths) == 1:
        return [np.load(paths[0], mmap_mode="r")]
    return Parallel(n_jobs=TYPICALITY_MATERIALIZE_JOBS, prefer="threads")(
        delayed(lambda path: np.load(path, mmap_mode="r"))(path) for path in paths
    )


def _load_embedding_stack(df: pd.DataFrame, detector: str) -> np.ndarray:
    paths = df[f"{detector}_embedding_path"].astype(str).tolist()
    return np.stack(_parallel_load_embeddings(paths), axis=0)


def _load_embedding_stack_batched(paths: list[str], batch_size: int) -> np.ndarray:
    """Load many .npy embeddings in chunks to limit peak RAM (np.stack copies mmap data)."""
    if not paths:
        return np.empty((0, 0), dtype=np.float32)
    chunks: list[np.ndarray] = []
    for start in range(0, len(paths), batch_size):
        batch_paths = paths[start : start + batch_size]
        chunks.append(np.stack(_parallel_load_embeddings(batch_paths), axis=0))
    return np.concatenate(chunks, axis=0)


def _build_typicality_refs(
    train_df: pd.DataFrame,
    selected_detectors: tuple[str, ...],
    *,
    k: int | None = None,
    distance: str | None = None,
) -> dict[str, TypicalityReference]:
    k = TYPICALITY_K if k is None else k
    distance = TYPICALITY_DISTANCE if distance is None else distance
    refs: dict[str, TypicalityReference] = {}
    for detector in selected_detectors:
        real_df = train_df[train_df["y_fake"].eq(0)]
        spoof_df = train_df[train_df["y_fake"].eq(1)]
        real_emb = _load_embedding_stack_batched(
            real_df[f"{detector}_embedding_path"].astype(str).tolist(),
            TYPICALITY_MATERIALIZE_BATCH,
        )
        spoof_emb = _load_embedding_stack_batched(
            spoof_df[f"{detector}_embedding_path"].astype(str).tolist(),
            TYPICALITY_MATERIALIZE_BATCH,
        )
        refs[detector] = build_typicality_reference(
            detector=detector,
            distance=distance,  # type: ignore[arg-type]
            k=k,
            real_embeddings=real_emb,
            synthetic_embeddings=spoof_emb,
            real_ids=[str(r.get("sample_id", idx)) for idx, r in real_df.iterrows()],
            synthetic_ids=[str(r.get("sample_id", idx)) for idx, r in spoof_df.iterrows()],
        )
    return refs


def _materialize_typicality_features(
    split: pd.DataFrame,
    refs: dict[str, TypicalityReference],
    selected_detectors: tuple[str, ...],
    *,
    system: str = TYPICALITY_SYSTEM,
    eps: float = DEFAULT_TYPICALITY_EPS,
    on_progress: ProgressCallback | None = None,
    progress_lo: int = 25,
    progress_hi: int = 70,
) -> pd.DataFrame:
    from core.latent_typicality.features import feature_columns_for_detectors
    from core.latent_typicality.typicality import typicality_features_batch

    total = len(split)
    if total == 0:
        return split.copy()

    exclude_self = split["reference_split"].eq("train_logreg").to_numpy()
    feature_cols = feature_columns_for_detectors(system, selected_detectors)
    feature_arrays: dict[str, np.ndarray] = {}

    for det_idx, detector in enumerate(selected_detectors):
        feature_arrays[f"S_{detector}"] = split[f"{detector}_bonafide_logit"].to_numpy(dtype=float)
        paths = split[f"{detector}_embedding_path"].astype(str).tolist()
        chunk_parts: dict[str, list[np.ndarray]] = {}
        for start in range(0, total, TYPICALITY_MATERIALIZE_BATCH):
            end = min(start + TYPICALITY_MATERIALIZE_BATCH, total)
            chunk_emb = np.stack(
                _parallel_load_embeddings(paths[start:end]),
                axis=0,
            )
            chunk_feats = typicality_features_batch(
                chunk_emb,
                refs[detector],
                eps=eps,
                exclude_self=exclude_self[start:end],
            )
            for key, values in chunk_feats.items():
                chunk_parts.setdefault(key, []).append(values)
            del chunk_emb
        for key, parts in chunk_parts.items():
            feature_arrays[key] = np.concatenate(parts, axis=0)
        if on_progress is not None:
            span = max(1, progress_hi - progress_lo)
            pct = progress_lo + int(span * (det_idx + 1) / len(selected_detectors))
            report_progress(
                on_progress,
                pct,
                f"Materializando features k-NN (sistema D): detector {det_idx + 1}/{len(selected_detectors)}",
            )

    feat_df = pd.DataFrame({col: feature_arrays[col] for col in feature_cols})
    out = split.copy().reset_index(drop=True)
    for col in feat_df.columns:
        out[col] = feat_df[col].values
    if on_progress is not None:
        report_progress(
            on_progress,
            progress_hi,
            f"Materializando features k-NN (sistema D): {total:,}/{total:,}",
        )
    return out


def _build_questioned_features(
    detector_scores: dict[str, Any],
    refs: dict[str, TypicalityReference],
    selected_detectors: tuple[str, ...],
    *,
    system: str = TYPICALITY_SYSTEM,
    eps: float = DEFAULT_TYPICALITY_EPS,
) -> np.ndarray:
    row: dict[str, float] = {}
    embeddings: dict[str, np.ndarray] = {}
    for detector in selected_detectors:
        scores = detector_scores.get(detector) or {}
        if scores.get("bonafide_logit") is not None:
            row[f"{detector}_bonafide_logit"] = float(scores["bonafide_logit"])
        else:
            prob = float(scores.get("bonafide_prob", 0.5))
            prob = min(max(prob, 1e-6), 1.0 - 1e-6)
            row[f"{detector}_bonafide_logit"] = float(math.log(prob / (1.0 - prob)))
        embedding = scores.get("embedding")
        if embedding is None:
            raise RuntimeError(f"Embedding ausente para detector {detector} (tipicidade latente)")
        embeddings[detector] = np.asarray(embedding, dtype=np.float32)
    feats = build_system_features_for_detectors(
        pd.Series(row),
        system=system,
        refs=refs,
        embeddings=embeddings,
        detectors=selected_detectors,
        eps=eps,
        exclude_self=False,
    )
    cols = feature_columns_for_detectors(system, selected_detectors)
    return np.array([float(feats[col]) for col in cols], dtype=float)


def _save_audio_lr_cache(
    *,
    cache_key: str,
    model: Any,
    calibration: dict[str, Any],
    feature_cols: list[str],
    selected_detectors: tuple[str, ...],
    metadata: dict[str, Any],
    scored: pd.DataFrame | None = None,
    typicality_refs: dict[str, TypicalityReference] | None = None,
) -> Path:
    path = _cache_dir() / f"{cache_key}.joblib"
    payload: dict[str, Any] = {
        "model": model,
        "feature_cols": feature_cols,
        "calibration": _serialize_calibration(calibration),
        "selected_detectors": list(selected_detectors),
        "metadata": metadata,
    }
    if scored is not None:
        payload["scored"] = scored
    if typicality_refs is not None:
        payload["typicality_refs"] = typicality_refs
    joblib.dump(payload, path)
    return path


def _load_audio_lr_cache(
    cache_key: str,
) -> tuple[Any, dict[str, Any], list[str], tuple[str, ...], pd.DataFrame | None, dict[str, TypicalityReference] | None] | None:
    cached = _load_lr_cache(cache_key)
    if cached is None:
        return None
    model, calibration, feature_cols, selected_detectors, scored = cached
    path = _cache_dir() / f"{cache_key}.joblib"
    typicality_refs = None
    if path.is_file():
        try:
            data = joblib.load(path)
            typicality_refs = data.get("typicality_refs")
        except Exception:
            typicality_refs = None
    return model, calibration, feature_cols, selected_detectors, scored, typicality_refs


def _assign_splits(sample: pd.DataFrame, seed: int, sample_multiplier: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 1)
    parts: list[pd.DataFrame] = []
    train_per_class = TRAIN_PER_CLASS * sample_multiplier
    calib_per_class = CALIB_PER_CLASS * sample_multiplier
    test_per_class = TEST_PER_CLASS * sample_multiplier
    for (_key, y_fake), group in sample.groupby(["reference_key", "y_fake"], sort=True):
        shuffled = group.sample(frac=1.0, random_state=int(rng.integers(0, 2**31 - 1))).copy()
        shuffled["reference_split"] = (
            ["train_logreg"] * train_per_class
            + ["calibration_bigauss"] * calib_per_class
            + ["test_bigauss"] * test_per_class
        )
        parts.append(shuffled)
    return pd.concat(parts, ignore_index=True)


def _cache_key(
    *,
    score_matrix: Path,
    roles: ReferenceSelectionRoles,
    selected_detectors: tuple[str, ...],
    classifier: str,
    seed: int,
    sample_multiplier: int = 1,
    use_latent_typicality: bool = False,
    typicality_k: int = TYPICALITY_K,
    typicality_distance: str = TYPICALITY_DISTANCE,
    typicality_system: str = TYPICALITY_SYSTEM,
) -> str:
    import hashlib

    canonical = {
        "kind": "audio_spoofing_lr",
        "score_matrix_hash": _score_matrix_hash(score_matrix),
        "fit_items": sorted(item.key for item in roles.fit_items),
        "test_items": sorted(item.key for item in roles.test_items),
        "selected_detectors": list(selected_detectors),
        "classifier": classifier,
        "seed": seed,
        "sample_multiplier": sample_multiplier,
        "sample_per_class": SAMPLE_PER_CLASS,
        "use_latent_typicality": use_latent_typicality,
        "typicality_k": typicality_k if use_latent_typicality else None,
        "typicality_distance": typicality_distance if use_latent_typicality else None,
        "typicality_system": typicality_system if use_latent_typicality else None,
    }
    payload = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _detector_features(detector_scores: dict[str, Any], selected_detectors: tuple[str, ...]) -> np.ndarray:
    missing = [detector for detector in selected_detectors if detector not in detector_scores]
    if missing:
        raise RuntimeError("LR exige os detectores selecionados. Ausentes: " + ", ".join(missing))
    values: list[float] = []
    for detector in selected_detectors:
        scores = detector_scores[detector] or {}
        if scores.get("bonafide_logit") is not None:
            values.append(float(scores["bonafide_logit"]))
            continue
        prob = float(scores.get("bonafide_prob", 0.5))
        eps = 1e-6
        prob = min(max(prob, eps), 1.0 - eps)
        values.append(float(math.log(prob / (1.0 - prob))))
    return np.array(values, dtype=float)


def _write_summary_txt(path: Path, report: dict[str, Any]) -> None:
    q = report.get("questioned", {})
    metrics = report.get("test_metrics", {})
    items = report.get("selected_items", [])
    feature_weights = report.get("feature_weights", {})
    classifier_label = report.get("meta_classifier_label", _classifier_label(DEFAULT_META_CLASSIFIER))
    lines: list[str] = [
        "RELATORIO DE CALIBRACAO LR - SPOOFING DE AUDIO",
        "=" * 60,
        "",
        f"Hipese positiva (H1): {report.get('hypothesis_positive', 'bonafide_authentic')}",
        f"Hipese negativa (H0): {report.get('hypothesis_negative', 'spoof_synthetic')}",
        "",
        "EVIDENCIA QUESTIONADA",
        "-" * 60,
        f"log10(LR) = {q.get('log10_lr', '—')}",
        f"LR        = {q.get('lr', '—')}",
        f"z score   = {q.get('logreg_z', '—')}",
        "",
        "MODELO META-CLASSIFICADOR",
        "-" * 60,
        f"Algoritmo: {classifier_label}",
        f"Identificador: {report.get('meta_classifier', DEFAULT_META_CLASSIFIER)}",
        "",
        "METRICAS DA POPULACAO DE REFERENCIA (conjunto de teste)",
        "-" * 60,
        f"CLLR     = {metrics.get('cllr', '—')}",
        f"minCLLR  = {metrics.get('min_cllr', '—')}",
        f"EER      = {metrics.get('eer', '—')}",
        f"AUC      = {metrics.get('auc', '—')}",
        f"Amostras = {metrics.get('rows', '—')} (bonafide={metrics.get('real_rows', '—')}, spoof={metrics.get('fake_rows', '—')})",
        "",
        "POPULACAO SELECIONADA",
        "-" * 60,
        f"Subgrupos: {report.get('selected_count', '—')}",
        f"  Fit (treino+calib): {report.get('fit_count', report.get('selected_count', '—'))}",
        f"  Teste (metricas): {report.get('test_count', report.get('selected_count', '—'))}",
        f"Amostras por classe/subgrupo: {report.get('sample_per_class_per_subgroup', '—')}",
    ]
    if report.get("augmented_reference"):
        lines.extend(
            [
                f"Referencia aumentada: sim (multiplicador={report.get('sample_multiplier', '—')})",
                f"Augmentacoes: {', '.join(AUGMENTATION_NAMES)}",
            ]
        )
    for item in items:
        lines.append(f"  - {item.get('base_group', '')} / {item.get('subgroup', '')}")
    if feature_weights:
        lines.extend(
            [
                "",
                "PESOS / IMPORTANCIA DOS DETECTORES",
                "-" * 60,
            ]
        )
        for name, value in feature_weights.items():
            lines.append(f"  {name} = {value}")
    if report.get("logreg_intercept") is not None:
        lines.append(f"  intercepto = {report.get('logreg_intercept')}")
    lines.extend(
        [
            "",
            "NOTA",
            "-" * 60,
            report.get(
                "note",
                "LR > 1 favorece H1=bonafide/autentico; LR < 1 favorece H0=spoof/sintetico.",
            ),
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _build_report(
    *,
    model: Any,
    calibration: dict[str, Any],
    feature_cols: list[str],
    selected_detectors: tuple[str, ...],
    roles: ReferenceSelectionRoles,
    split: pd.DataFrame,
    detector_scores: dict[str, Any],
    classifier: str,
    out_dir: Path,
    used_cache: bool,
    sample_multiplier: int = 1,
    augmented_reference: bool = False,
    scored: pd.DataFrame | None = None,
    use_latent_typicality: bool = False,
    typicality_refs: dict[str, TypicalityReference] | None = None,
) -> dict[str, Any]:
    if scored is None:
        scored = _score_dataframe(split, model, calibration, feature_cols)
    test = scored[scored["reference_split"].eq(TEST_REFERENCE_SPLIT)].copy()

    if use_latent_typicality:
        if typicality_refs is None:
            raise RuntimeError("typicality_refs ausente para LR com tipicidade latente")
        features = _build_questioned_features(detector_scores, typicality_refs, selected_detectors)
    else:
        features = _detector_features(detector_scores, selected_detectors)
    questioned = _apply(model, calibration, features)

    plot_dir = out_dir
    tippett_name = "lr_reference_tippett.png"
    distribution_name = "lr_reference_distribution.png"
    identity_name = "lr_reference_identity.png"
    summary_name = "lr_reference_summary.txt"
    _plot_tippett(plot_dir / tippett_name, test, "Tippett plot — spoofing de audio")
    _plot_distribution(
        plot_dir / distribution_name,
        test,
        "Distribuicao das LRs — populacao de referencia (audio)",
        questioned_log10_lr=questioned.get("log10_lr"),
    )
    identity_mse = _plot_identity(
        plot_dir / identity_name,
        test,
        "Funcao identidade — populacao de referencia (audio)",
    )

    feature_weights = _classifier_feature_importance(model, feature_cols)
    report: dict[str, Any] = {
        "hypothesis_positive": "bonafide_authentic",
        "hypothesis_negative": "spoof_synthetic",
        "sample_per_class_per_subgroup": SAMPLE_PER_CLASS,
        "selected_items": [
            {"base_group": item.base_group, "subgroup": item.subgroup, "key": item.key}
            for item in roles.union_items
        ],
        "selected_count": len(roles.union_items),
        "fit_items": [
            {"base_group": item.base_group, "subgroup": item.subgroup, "key": item.key}
            for item in roles.fit_items
        ],
        "test_items": [
            {"base_group": item.base_group, "subgroup": item.subgroup, "key": item.key}
            for item in roles.test_items
        ],
        "fit_count": len(roles.fit_items),
        "test_count": len(roles.test_items),
        "split_roles_separated": roles.fit_keys != roles.test_keys
            or roles.fit_items != roles.test_items,
        "sample_rows": int(len(split)),
        "fit_sample_rows": int(
            split["reference_split"].astype(str).isin(FIT_REFERENCE_SPLITS).sum()
        ),
        "test_sample_rows": int(
            (split["reference_split"].astype(str) == TEST_REFERENCE_SPLIT).sum()
        ),
        "sample_multiplier": int(sample_multiplier),
        "augmented_reference": bool(augmented_reference),
        "selected_detectors": list(selected_detectors),
        "meta_classifier": classifier,
        "meta_classifier_label": _classifier_label(classifier),
        "test_metrics": _metrics(test),
        "identity_mse": identity_mse,
        "bigauss": {
            "variant": "EER",
            "eer": calibration["eer"],
            "sigma": calibration["sigma"],
            "mu_fake": calibration["mu_fake"],
            "mu_real": calibration["mu_real"],
        },
        "feature_weights": feature_weights,
        "questioned": {
            "log10_lr": questioned.get("log10_lr"),
            "lr": questioned.get("lr"),
            "logreg_z": questioned.get("logreg_z"),
            "cdf_p": questioned.get("cdf_p"),
        },
        "artifact_filenames": {
            "tippett": tippett_name,
            "distribution": distribution_name,
            "identity": identity_name,
            "summary": summary_name,
        },
        "note": "LR > 1 favorece H1=bonafide/autentico; LR < 1 favorece H0=spoof/sintetico.",
        "used_cache": used_cache,
        "latent_typicality": bool(use_latent_typicality),
    }
    if use_latent_typicality:
        report["typicality_config"] = {
            "system": TYPICALITY_SYSTEM,
            "distance": TYPICALITY_DISTANCE,
            "k": TYPICALITY_K,
        }
    if classifier == "logistic":
        report["logreg_coefficients"] = feature_weights
        if hasattr(model, "intercept_"):
            report["logreg_intercept"] = float(model.intercept_[0])
    _write_json(out_dir / "lr_reference_report.json", report)
    _write_summary_txt(out_dir / summary_name, report)
    joblib.dump(
        {
            "model": model,
            "feature_cols": feature_cols,
            "calibration": _serialize_calibration(calibration),
            "selected_items": report["selected_items"],
            "selected_detectors": report["selected_detectors"],
        },
        out_dir / "lr_reference_model.joblib",
    )
    test.to_csv(out_dir / "lr_reference_test_scored.csv", index=False)
    return report


def compute_reference_lr(
    *,
    detector_scores: dict[str, Any],
    selection: Any,
    out_dir: Path,
    seed: int = 20260704,
    score_matrix: Path = DEFAULT_SCORE_MATRIX,
    selected_detectors: tuple[str, ...] = ALL_DETECTORS,
    classifier: str = DEFAULT_META_CLASSIFIER,
    sample_multiplier: int = 1,
    use_latent_typicality: bool = False,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    selected_detectors = tuple(detector for detector in ALL_DETECTORS if detector in selected_detectors)
    if not selected_detectors:
        raise RuntimeError("Pelo menos um detector deve ser selecionado para calibracao LR.")
    classifier = _validate_classifier(classifier)
    sample_multiplier = max(1, int(sample_multiplier))
    augmented_reference = sample_multiplier > 1
    out_dir.mkdir(parents=True, exist_ok=True)
    report_progress(on_progress, 8, "Carregando matriz de referencia LR…")

    if use_latent_typicality:
        score_matrix = DEFAULT_REPRESENTATIONS_MATRIX
        feature_cols = feature_columns_for_detectors(TYPICALITY_SYSTEM, selected_detectors)
    else:
        feature_cols = _feature_cols(selected_detectors)

    roles = normalize_reference_selection_roles(selection)
    if not roles.fit_items:
        raise RuntimeError("Pelo menos um subgrupo em fit_items e necessario para calibracao LR.")
    if not roles.test_items:
        raise RuntimeError("Pelo menos um subgrupo em test_items e necessario para metricas de teste.")
    union_items = list(roles.union_items)
    if not score_matrix.is_file():
        raise RuntimeError(f"Score matrix nao encontrada: {score_matrix}")
    df = _load_scores(score_matrix)
    if use_latent_typicality:
        before = len(df)
        df = _filter_rows_with_embeddings(df)
        if df.empty:
            raise RuntimeError("Nenhuma linha com embeddings completos no disco para calibracao com tipicidade.")
        if len(df) < before:
            report_progress(
                on_progress,
                12,
                f"Matriz filtrada: {len(df):,}/{before:,} linhas com embeddings no disco",
            )
    else:
        before = len(df)
        df = _filter_rows_with_finite_features(df, feature_cols)
        if df.empty:
            raise RuntimeError("Nenhuma linha com logits finitos dos detectores para calibracao LR.")
        if len(df) < before:
            report_progress(
                on_progress,
                12,
                f"Matriz filtrada: {len(df):,}/{before:,} linhas com logits finitos",
            )
    df = _filter_matrix_scope(df, augmented_reference=augmented_reference)
    sample = _build_reference_sample(df, union_items, seed, sample_multiplier=sample_multiplier)
    split = _assign_splits(sample, seed, sample_multiplier=sample_multiplier)
    split = _filter_working_split(split, roles)
    aug_label = f", aumentada x{sample_multiplier}" if augmented_reference else ""
    tip_label = ", tipicidade latente" if use_latent_typicality else ""
    role_label = (
        f" (fit {len(roles.fit_items)}, test {len(roles.test_items)})"
        if roles.fit_keys != roles.test_keys or roles.fit_items != roles.test_items
        else ""
    )
    report_progress(
        on_progress,
        18,
        f"Amostra LR: {len(split):,} linhas ({len(union_items)} subgrupos{role_label}{aug_label}{tip_label})",
    )

    cache_key = _cache_key(
        score_matrix=score_matrix,
        roles=roles,
        selected_detectors=selected_detectors,
        classifier=classifier,
        seed=seed,
        sample_multiplier=sample_multiplier,
        use_latent_typicality=use_latent_typicality,
    )
    cached = _load_audio_lr_cache(cache_key) if use_latent_typicality else _load_lr_cache(cache_key)
    used_cache = False
    scored: pd.DataFrame | None = None
    model = None
    calibration = None
    typicality_refs: dict[str, TypicalityReference] | None = None

    if cached is not None:
        if use_latent_typicality:
            model, calibration, cached_feature_cols, cached_detectors, scored, typicality_refs = cached
        else:
            model, calibration, cached_feature_cols, cached_detectors, scored = cached
            typicality_refs = None
        if cached_feature_cols == feature_cols and cached_detectors == selected_detectors:
            used_cache = True
            report_progress(on_progress, 45, "Cache de calibracao LR encontrado — reutilizando modelo")
        else:
            cached = None
            scored = None
            typicality_refs = None

    if cached is None:
        if use_latent_typicality:
            report_progress(on_progress, 22, "Construindo bancos k-NN no split de treino (anti-leak)…")
            train_df = split[split["reference_split"].eq("train_logreg")].copy()
            typicality_refs = _build_typicality_refs(train_df, selected_detectors)
            split = _materialize_typicality_features(
                split,
                typicality_refs,
                selected_detectors,
                on_progress=on_progress,
                progress_lo=25,
                progress_hi=70,
            )
            # Belt-and-suspenders: typicality features (incl. S_*, which mirror the raw
            # detector logit) must be finite before the meta-classifier sees them. Any
            # residual non-finite row (e.g. a stray stale score) is dropped here so
            # calibration never crashes with "Input X contains NaN".
            before_tip = len(split)
            split = _filter_rows_with_finite_features(split, feature_cols)
            if split.empty:
                raise RuntimeError(
                    "Nenhuma linha com features de tipicidade finitas para calibracao LR."
                )
            if len(split) < before_tip:
                report_progress(
                    on_progress,
                    71,
                    f"Features de tipicidade filtradas: {len(split):,}/{before_tip:,} linhas finitas",
                )
        else:
            report_progress(on_progress, 35, "Preparando logits dos detectores para treino LR…")
        train = split[split["reference_split"].eq("train_logreg")]
        x_train = train[feature_cols].to_numpy(dtype=float)
        y_train = (1 - train["y_fake"].astype(int)).to_numpy()
        report_progress(
            on_progress,
            72,
            f"Treinando meta-classificador ({classifier}) em {len(train):,} amostras…",
        )
        model = _train_meta_classifier(classifier, x_train, y_train, feature_cols, seed)
        report_progress(on_progress, 85, "Calibracao bi-Gaussiana (EER) na populacao de referencia…")
        calibration = _fit_bigauss(split, model, feature_cols)

    if scored is None:
        scored = _score_dataframe(split, model, calibration, feature_cols)
        metadata = {
            "kind": "audio_spoofing_lr",
            "classifier": classifier,
            "seed": seed,
            "selected_count": len(roles.union_items),
            "fit_count": len(roles.fit_items),
            "test_count": len(roles.test_items),
            "score_matrix_hash": _score_matrix_hash(score_matrix),
            "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "use_latent_typicality": use_latent_typicality,
        }
        if use_latent_typicality:
            _save_audio_lr_cache(
                cache_key=cache_key,
                model=model,
                calibration=calibration,
                feature_cols=feature_cols,
                selected_detectors=selected_detectors,
                metadata=metadata,
                scored=scored,
                typicality_refs=typicality_refs,
            )
        else:
            _save_lr_cache(
                cache_key=cache_key,
                model=model,
                calibration=calibration,
                feature_cols=feature_cols,
                selected_detectors=selected_detectors,
                metadata=metadata,
                scored=scored,
            )

    report_progress(on_progress, 92, "Gerando graficos Tippett e relatorio LR…")
    return _build_report(
        model=model,
        calibration=calibration,
        feature_cols=feature_cols,
        selected_detectors=selected_detectors,
        roles=roles,
        split=split,
        detector_scores=detector_scores,
        classifier=classifier,
        out_dir=out_dir,
        used_cache=used_cache,
        sample_multiplier=sample_multiplier,
        augmented_reference=augmented_reference,
        scored=scored,
        use_latent_typicality=use_latent_typicality,
        typicality_refs=typicality_refs,
    )
