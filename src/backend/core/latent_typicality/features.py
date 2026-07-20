"""Feature builders for systems A/B/C/D."""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from core.latent_typicality.typicality import TypicalityReference, typicality_features_for_embedding

DETECTORS = ("df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa")
SCORE_COLS = [f"{detector}_bonafide_logit" for detector in DETECTORS]


def build_system_features(
    row: pd.Series,
    *,
    system: str,
    refs: dict[str, TypicalityReference],
    embeddings: dict[str, np.ndarray],
    eps: float = 1e-8,
    exclude_self: bool = False,
) -> dict[str, float]:
    features: dict[str, float] = {}
    for detector in DETECTORS:
        score_col = f"{detector}_bonafide_logit"
        features[f"S_{detector}"] = float(row[score_col])

    typicality: dict[str, float] = {}
    for detector in DETECTORS:
        ref = refs[detector]
        emb = embeddings[detector]
        typicality.update(
            typicality_features_for_embedding(emb, ref, eps=eps, exclude_self=exclude_self)
        )

    if system == "A":
        return {f"S_{detector}": features[f"S_{detector}"] for detector in DETECTORS}

    out = dict(features)
    for detector in DETECTORS:
        out[f"T_R_{detector}"] = typicality[f"T_R_{detector}"]
        out[f"T_S_{detector}"] = typicality[f"T_S_{detector}"]

    if system == "B":
        return {
            **{f"S_{detector}": out[f"S_{detector}"] for detector in DETECTORS},
            **{
                key: out[key]
                for detector in DETECTORS
                for key in (f"T_R_{detector}", f"T_S_{detector}")
            },
        }

    for detector in DETECTORS:
        out[f"OOD_{detector}"] = typicality[f"OOD_{detector}"]

    if system == "C":
        keys = [f"S_{d}" for d in DETECTORS]
        keys += [f"T_R_{d}" for d in DETECTORS] + [f"T_S_{d}" for d in DETECTORS]
        keys += [f"OOD_{d}" for d in DETECTORS]
        return {key: out[key] for key in keys}

    for detector in DETECTORS:
        out[f"Delta_r_{detector}"] = typicality[f"Delta_r_{detector}"]
        out[f"rho_{detector}"] = typicality[f"rho_{detector}"]

    return out


def feature_columns(system: str) -> list[str]:
    cols = [f"S_{d}" for d in DETECTORS]
    if system == "A":
        return cols
    cols += [f"T_R_{d}" for d in DETECTORS] + [f"T_S_{d}" for d in DETECTORS]
    if system == "B":
        return cols
    cols += [f"OOD_{d}" for d in DETECTORS]
    if system == "C":
        return cols
    cols += [f"Delta_r_{d}" for d in DETECTORS] + [f"rho_{d}" for d in DETECTORS]
    return cols


def feature_columns_for_detectors(system: str, detectors: tuple[str, ...]) -> list[str]:
    cols = [f"S_{d}" for d in detectors]
    if system == "A":
        return cols
    cols += [f"T_R_{d}" for d in detectors] + [f"T_S_{d}" for d in detectors]
    if system == "B":
        return cols
    cols += [f"OOD_{d}" for d in detectors]
    if system == "C":
        return cols
    cols += [f"Delta_r_{d}" for d in detectors] + [f"rho_{d}" for d in detectors]
    return cols


def build_system_features_for_detectors(
    row: pd.Series,
    *,
    system: str,
    refs: dict[str, TypicalityReference],
    embeddings: dict[str, np.ndarray],
    detectors: tuple[str, ...],
    eps: float = 1e-8,
    exclude_self: bool = False,
) -> dict[str, float]:
    features: dict[str, float] = {}
    for detector in detectors:
        score_col = f"{detector}_bonafide_logit"
        features[f"S_{detector}"] = float(row[score_col])

    typicality: dict[str, float] = {}
    for detector in detectors:
        ref = refs[detector]
        emb = embeddings[detector]
        typicality.update(
            typicality_features_for_embedding(emb, ref, eps=eps, exclude_self=exclude_self)
        )

    if system == "A":
        return {f"S_{detector}": features[f"S_{detector}"] for detector in detectors}

    out = dict(features)
    for detector in detectors:
        out[f"T_R_{detector}"] = typicality[f"T_R_{detector}"]
        out[f"T_S_{detector}"] = typicality[f"T_S_{detector}"]

    if system == "B":
        return {
            **{f"S_{detector}": out[f"S_{detector}"] for detector in detectors},
            **{
                key: out[key]
                for detector in detectors
                for key in (f"T_R_{detector}", f"T_S_{detector}")
            },
        }

    for detector in detectors:
        out[f"OOD_{detector}"] = typicality[f"OOD_{detector}"]

    if system == "C":
        keys = [f"S_{d}" for d in detectors]
        keys += [f"T_R_{d}" for d in detectors] + [f"T_S_{d}" for d in detectors]
        keys += [f"OOD_{d}" for d in detectors]
        return {key: out[key] for key in keys}

    for detector in detectors:
        out[f"Delta_r_{detector}"] = typicality[f"Delta_r_{detector}"]
        out[f"rho_{detector}"] = typicality[f"rho_{detector}"]

    return out


def rows_to_feature_matrix(
    df: pd.DataFrame,
    feature_rows: Iterable[dict[str, float]],
    system: str,
) -> tuple[np.ndarray, list[str]]:
    cols = feature_columns(system)
    matrix = np.array([[float(row[col]) for col in cols] for row in feature_rows], dtype=float)
    return matrix, cols
