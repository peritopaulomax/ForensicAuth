"""Reference-population LR calibration for synthetic-image detection.

Prototype service for a selectable reference population:
- uses stored detector scores as the reference population;
- trains a meta-classifier (logistic | xgboost) on detector logit features;
- calibrates the meta-score with EER-based bi-Gaussianized calibration;
- reports LR with positive values favoring H1 = real/authentic.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import matplotlib
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from scipy.optimize import brentq
from scipy.stats import gaussian_kde, norm
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve
from xgboost import XGBClassifier

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

try:
    from core.latent_typicality.config import (
        DEFAULT_DISTANCE as DEFAULT_TYPICALITY_DISTANCE_FROM_CONFIG,
        DEFAULT_K as DEFAULT_TYPICALITY_K_FROM_CONFIG,
        DEFAULT_SYSTEM as DEFAULT_TYPICALITY_SYSTEM_FROM_CONFIG,
    )
    from core.latent_typicality.features import feature_columns_for_detectors
    from core.latent_typicality.representations_utils import (
        ORIGINAL_AUGMENTATION_TAG,
        load_embeddings_row,
        resolve_embedding_path,
        row_has_embeddings,
    )
    from core.latent_typicality.typicality import (
        TypicalityReference,
        build_typicality_reference,
        typicality_features_batch,
    )
except ImportError:
    ORIGINAL_AUGMENTATION_TAG = "original"
    DEFAULT_TYPICALITY_DISTANCE_FROM_CONFIG = "cosine"
    DEFAULT_TYPICALITY_K_FROM_CONFIG = 5
    DEFAULT_TYPICALITY_SYSTEM_FROM_CONFIG = "D"
    feature_columns_for_detectors = None  # type: ignore[assignment]
    load_embeddings_row = None  # type: ignore[assignment]
    resolve_embedding_path = None  # type: ignore[assignment]
    row_has_embeddings = None  # type: ignore[assignment]
    build_typicality_reference = None  # type: ignore[assignment]
    typicality_features_batch = None  # type: ignore[assignment]
    TypicalityReference = None  # type: ignore[assignment,misc]


ALL_DETECTORS = ("ai_image_detector_deploy", "sdxl_flux_detector_v1_1", "bfree", "corvi2023", "safe")
FEATURE_COLS_FOR_DETECTORS = {detector: f"{detector}_logit_prob" for detector in ALL_DETECTORS}
from core.reference_data.paths import (
    lr_cache_dir as _reference_lr_cache_dir,
    project_root as _project_root_fn,
    synthetic_augmented_score_matrix as _synthetic_augmented_score_matrix,
    synthetic_representations_matrix as _synthetic_representations_matrix,
    synthetic_score_matrix as _synthetic_score_matrix,
)

PROJECT_ROOT = _project_root_fn()
DEFAULT_SCORE_MATRIX = _synthetic_score_matrix()
DEFAULT_AUGMENTED_SCORE_MATRIX = _synthetic_augmented_score_matrix()
DEFAULT_REPRESENTATIONS_MATRIX = _synthetic_representations_matrix()
_SCORE_ONLY_MATRICES = frozenset(
    {
        DEFAULT_SCORE_MATRIX.resolve(),
        DEFAULT_AUGMENTED_SCORE_MATRIX.resolve(),
    }
)
AUGMENTATION_NAMES: tuple[str, ...] = ("jpeg_85", "webp_80", "crop_upscale", "resize_down_50")
AUGMENTATION_MULTIPLIER = 1 + len(AUGMENTATION_NAMES)
SAMPLE_PER_CLASS = 500
TRAIN_PER_CLASS = 250
CALIB_PER_CLASS = 125
TEST_PER_CLASS = 125

# Latent typicality defaults (mirror audio_spoofing_lr_reference.py).
DEFAULT_TYPICALITY_SYSTEM = "D"
DEFAULT_TYPICALITY_DISTANCE = "cosine"
DEFAULT_TYPICALITY_K = 5
TYPICALITY_MATERIALIZE_BATCH = max(
    32, int(os.environ.get("VA_LR_TYPICALITY_BATCH", "512"))
)
TYPICALITY_MATERIALIZE_JOBS = min(
    12, max(1, int(os.environ.get("VA_LR_TYPICALITY_JOBS", "8")))
)

# In-memory caches to avoid repeated I/O and scoring on the same reference population.
# Key for score matrix: (resolved path string, mtime, size).
_SCORE_MATRIX_DF_CACHE: dict[tuple[str, float, int], pd.DataFrame] = {}
# Key for scored reference population: cache_key from compute_reference_lr.
_LR_SCORED_CACHE: dict[str, pd.DataFrame] = {}

META_CLASSIFIERS = (
    "logistic",
    "xgboost",
)
DEFAULT_META_CLASSIFIER = "logistic"

# Aliases aceitos de manifests/scaffold legados → id canônico.
_CLASSIFIER_ALIASES: dict[str, str] = {
    "logistic_regression": "logistic",
    "logreg": "logistic",
    "xgb": "xgboost",
}

_CLASSIFIER_LABELS: dict[str, str] = {
    "logistic": "Regressao Logistica",
    "xgboost": "XGBoost",
}

BASE_LABELS = {
    "GenImage": "GenImage",
    "Defactify": "DeFactify / MS COCOAI",
    "AIGCDetectBenchmark": "AIGCDetectBenchmark",
    "OpenSDI": "OpenSDI",
    "AIGIBench_no_SocialRF": "AIGIBench sem SocialRF",
    "AIGIBench_SocialRF": "AIGIBench SocialRF",
    "Synthbuster": "Synthbuster",
    "BFree_extended_synthbuster": "BFree extended (Synthbuster)",
}

# Display metadata for the reference-population selector (description + associated paper).
BASE_CATALOG: dict[str, dict[str, str]] = {
    "GenImage": {
        "description": (
            "Benchmark million-scale: pares reais (ImageNet) e sinteticas de 8 geradores "
            "(GANs e difusao). Referencia classica para calibracao e generalizacao cross-generator."
        ),
        "paper_title": "GenImage: A Million-Scale Benchmark for Detecting AI-Generated Image",
        "paper_url": "https://arxiv.org/abs/2306.08571",
    },
    "Defactify": {
        "description": (
            "MS COCOAI (Defactify 4.0): reais MS COCO + sinteticas de SD 2.1, SDXL, SD3, "
            "DALL-E 3 e Midjourney v6 a partir das mesmas legendas. Split calibracao/validacao."
        ),
        "paper_title": "A Comprehensive Dataset for Human vs. AI Generated Image Detection",
        "paper_url": "https://arxiv.org/abs/2601.00553",
    },
    "AIGCDetectBenchmark": {
        "description": (
            "Benchmark de teste com 17 geradores (GANs + difusao); apenas split de avaliacao. "
            "Cobre ProGAN ate SDXL e APIs proprietarias."
        ),
        "paper_title": "PatchCraft / AIGCDetectBenchmark",
        "paper_url": "https://arxiv.org/abs/2311.12397",
    },
    "OpenSDI": {
        "description": (
            "OpenSDID (test): deteccao open-world de imagens de difusao (SD3, FLUX, etc.) "
            "com prompts diversos via VLMs. Subconjunto hard out-of-domain."
        ),
        "paper_title": "OpenSDI: Spotting Diffusion-Generated Images in the Open World",
        "paper_url": "https://arxiv.org/abs/2503.19653",
    },
    "AIGIBench_no_SocialRF": {
        "description": (
            "Subconjuntos de teste AIGIBench (SD3, FLUX, DALLE-3, CommunityAI): avaliacao "
            "de robustez e generalizacao multi-fonte sem SocialRF."
        ),
        "paper_title": "Is Artificial Intelligence Generated Image Detection a Solved Problem?",
        "paper_url": "https://arxiv.org/abs/2505.12335",
    },
    "AIGIBench_SocialRF": {
        "description": (
            "Subconjunto SocialRF do AIGIBench: imagens reais/sinteticas de redes sociais "
            "e NeRF/3D — cenario mais proximo do mundo real."
        ),
        "paper_title": "Is Artificial Intelligence Generated Image Detection a Solved Problem?",
        "paper_url": "https://arxiv.org/abs/2505.12335",
    },
    "Synthbuster": {
        "description": (
            "9 geradores de difusao (DALL-E, Midjourney, SD 1.x–XL, Firefly, GLIDE); "
            "legendas derivadas do RAISE. Benchmark externo; reais amostrados do AIGCDetect."
        ),
        "paper_title": "Synthbuster: Towards Detection of Diffusion Model Generated Images",
        "paper_url": "https://ieeexplore.ieee.org/document/10334046",
    },
    "BFree_extended_synthbuster": {
        "description": (
            "Extended Synthbuster (GRIP): RAISE reais + FLUX, SD3.5 e latent-diffusion. "
            "Conjunto de avaliacao do paper B-Free — nao e dado de treino do detector."
        ),
        "paper_title": "A Bias-Free Training Paradigm for More General AI-generated Image Detection",
        "paper_url": "https://arxiv.org/abs/2412.17671",
    },
}


def _base_catalog_entry(base_id: str) -> dict[str, str | None]:
    meta = BASE_CATALOG.get(base_id, {})
    return {
        "description": meta.get("description", ""),
        "paper_title": meta.get("paper_title") or None,
        "paper_url": meta.get("paper_url") or None,
    }

REFERENCE_CATALOG: dict[str, list[str]] = {
    "GenImage": [
        "ADM",
        "BigGAN",
        "Midjourney",
        "VQDM",
        "glide",
        "stable_diffusion_v_1_4",
        "stable_diffusion_v_1_5",
        "wukong",
    ],
    "Defactify": ["DALL-E_3", "Midjourney_v6", "SD2.1", "SD3", "SDXL"],
    "AIGCDetectBenchmark": [
        "ADM",
        "BigGAN",
        "CycleGAN",
        "DALLE2",
        "GLIDE",
        "GauGAN",
        "Midjourney",
        "ProGAN",
        "SD14",
        "SD15",
        "SDXL",
        "StarGAN",
        "StyleGAN",
        "StyleGAN2",
        "VQDM",
        "WhichFaceIsReal",
        "Wukong",
    ],
    "OpenSDI": ["flux", "sd3"],
    "AIGIBench_no_SocialRF": ["CommunityAI", "DALLE-3", "FLUX1-dev", "SD3"],
    "AIGIBench_SocialRF": ["SocialRF"],
    "Synthbuster": [
        "Adobe_Firefly",
        "DALL-E_2",
        "DALL-E_3",
        "GLIDE",
        "Midjourney_v5",
        "Stable_Diffusion_1.3",
        "Stable_Diffusion_1.4",
        "Stable_Diffusion_2",
        "Stable_Diffusion_XL",
    ],
    "BFree_extended_synthbuster": ["FLUX", "latent-diffusion"],
}


# Approximate public deployment / publication year for each synthetic generator.
# Used only for display purposes in the reference-population selector.
GENERATOR_DEPLOY_YEAR: dict[str, int | None] = {
    # GANs (older)
    "ProGAN": 2017,
    "StyleGAN": 2019,
    "StyleGAN2": 2019,
    "BigGAN": 2018,
    "CycleGAN": 2017,
    "StarGAN": 2018,
    "GauGAN": 2019,
    "WhichFaceIsReal": 2019,
    # Diffusion CNN-based (early)
    "ADM": 2021,
    "GLIDE": 2021,
    "DALLE2": 2022,
    "VQDM": 2022,
    "latent-diffusion": 2022,
    "Wukong": 2022,
    "wukong": 2022,
    "glide": 2021,
    "SD14": 2022,
    "SD15": 2022,
    "stable_diffusion_v_1_4": 2022,
    "stable_diffusion_v_1_5": 2022,
    "SD2.1": 2022,
    "Stable_Diffusion_1.3": 2022,
    "Stable_Diffusion_1.4": 2022,
    "Stable_Diffusion_2": 2022,
    # Diffusion CNN-based (modern)
    "SDXL": 2023,
    "Stable_Diffusion_XL": 2023,
    "Midjourney": 2022,
    "Midjourney_v5": 2023,
    "Midjourney_v6": 2023,
    # Diffusion Transformer-based
    "SD3": 2024,
    "sd3": 2024,
    "flux": 2024,
    "FLUX1-dev": 2024,
    "FLUX": 2024,
    "DALLE-3": 2023,
    "DALL-E_2": 2022,
    "DALL-E_3": 2023,
    "Adobe_Firefly": 2023,
    # Other neural
    "SocialRF": 2024,
    "CommunityAI": None,
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


# Default product population: Difusão Transformer + CNN moderna + AIGI Bench Social.
# Expanded at module init (and optionally overridden by populations/default_modern.yaml).
DEFAULT_MODERN_REFERENCE: tuple[PopulationItem, ...] = ()


def generator_deploy_year(generator: str) -> int | None:
    return GENERATOR_DEPLOY_YEAR.get(generator)


# Macro technology categories. Only synthetic (fake) generators are selectable;
# real images are sampled automatically by _build_reference_sample for balance.
REFERENCE_MACRO_CATEGORIES: dict[str, dict[str, Any]] = {
    "gan_older": {
        "label": "GANs (older)",
        "year_range": "2014–2019",
        "description": "Generative Adversarial Networks classicos: ProGAN, StyleGAN, BigGAN, CycleGAN, StarGAN, GauGAN, WhichFaceIsReal.",
        "items": [
            PopulationItem("AIGCDetectBenchmark", "ProGAN"),
            PopulationItem("AIGCDetectBenchmark", "StyleGAN"),
            PopulationItem("AIGCDetectBenchmark", "StyleGAN2"),
            PopulationItem("AIGCDetectBenchmark", "BigGAN"),
            PopulationItem("AIGCDetectBenchmark", "CycleGAN"),
            PopulationItem("AIGCDetectBenchmark", "StarGAN"),
            PopulationItem("AIGCDetectBenchmark", "GauGAN"),
            PopulationItem("AIGCDetectBenchmark", "WhichFaceIsReal"),
            PopulationItem("GenImage", "BigGAN"),
        ],
    },
    "diffusion_cnn_early": {
        "label": "Difusao CNN (antiga)",
        "year_range": "2021–2022",
        "description": "Modelos de difusao baseados em U-Net/CNN do inicio da era de difusao: ADM, GLIDE, DALLE2, VQDM, latent-diffusion, Stable Diffusion 1.x/2.x, Wukong.",
        "items": [
            PopulationItem("GenImage", "ADM"),
            PopulationItem("GenImage", "VQDM"),
            PopulationItem("GenImage", "glide"),
            PopulationItem("GenImage", "stable_diffusion_v_1_4"),
            PopulationItem("GenImage", "stable_diffusion_v_1_5"),
            PopulationItem("GenImage", "wukong"),
            PopulationItem("AIGCDetectBenchmark", "ADM"),
            PopulationItem("AIGCDetectBenchmark", "GLIDE"),
            PopulationItem("AIGCDetectBenchmark", "DALLE2"),
            PopulationItem("AIGCDetectBenchmark", "VQDM"),
            PopulationItem("AIGCDetectBenchmark", "SD14"),
            PopulationItem("AIGCDetectBenchmark", "SD15"),
            PopulationItem("AIGCDetectBenchmark", "Wukong"),
            PopulationItem("Defactify", "SD2.1"),
            PopulationItem("Synthbuster", "GLIDE"),
            PopulationItem("Synthbuster", "Stable_Diffusion_1.3"),
            PopulationItem("Synthbuster", "Stable_Diffusion_1.4"),
            PopulationItem("Synthbuster", "Stable_Diffusion_2"),
            PopulationItem("BFree_extended_synthbuster", "latent-diffusion"),
        ],
    },
    "diffusion_cnn_modern": {
        "label": "Difusao CNN (moderna)",
        "year_range": "2022–2024",
        "description": "Difusao U-Net/CNN de alta resolucao e modelos proprietarios modernos: SDXL, Stable Diffusion XL, Midjourney.",
        "items": [
            PopulationItem("GenImage", "Midjourney"),
            PopulationItem("AIGCDetectBenchmark", "Midjourney"),
            PopulationItem("AIGCDetectBenchmark", "SDXL"),
            PopulationItem("Defactify", "SDXL"),
            PopulationItem("Defactify", "Midjourney_v6"),
            PopulationItem("Synthbuster", "Stable_Diffusion_XL"),
            PopulationItem("Synthbuster", "Midjourney_v5"),
        ],
    },
    "diffusion_transformer": {
        "label": "Difusao Transformer",
        "year_range": "2023–2025",
        "description": "Modelos de difusao com backbone Transformer/DiT: SD3, FLUX, DALLE-3, Adobe Firefly.",
        "items": [
            PopulationItem("AIGIBench_no_SocialRF", "SD3"),
            PopulationItem("AIGIBench_no_SocialRF", "FLUX1-dev"),
            PopulationItem("AIGIBench_no_SocialRF", "DALLE-3"),
            PopulationItem("OpenSDI", "sd3"),
            PopulationItem("OpenSDI", "flux"),
            PopulationItem("Defactify", "SD3"),
            PopulationItem("Defactify", "DALL-E_3"),
            PopulationItem("Synthbuster", "Adobe_Firefly"),
            PopulationItem("Synthbuster", "DALL-E_2"),
            PopulationItem("Synthbuster", "DALL-E_3"),
            PopulationItem("BFree_extended_synthbuster", "FLUX"),
        ],
    },
    "other_neural": {
        "label": "Misto / outras arquiteturas",
        "year_range": "—",
        "description": "Arquiteturas nao enquadradas nos grupos anteriores: SocialRF (NeRF/3D), CommunityAI (API/mista).",
        "items": [
            PopulationItem("AIGIBench_SocialRF", "SocialRF"),
            PopulationItem("AIGIBench_no_SocialRF", "CommunityAI"),
        ],
    },
}


def refresh_reference_catalog_from_disk() -> str:
    """Reload macros/bases/default population from YAML under reference_data/. Returns source tag."""
    global REFERENCE_MACRO_CATEGORIES, REFERENCE_CATALOG, BASE_LABELS, BASE_CATALOG
    global DEFAULT_MODERN_REFERENCE, _item_to_macro_cache

    from core.reference_data.catalog_loader import load_macros, population_items

    fallback_bases = {
        base_id: {
            "label": BASE_LABELS.get(base_id, base_id),
            "generators": list(gens),
            **BASE_CATALOG.get(base_id, {}),
        }
        for base_id, gens in REFERENCE_CATALOG.items()
    }
    loaded = load_macros(
        "synthetic_image",
        item_factory=PopulationItem,
        fallback_macros=REFERENCE_MACRO_CATEGORIES,
        fallback_bases=fallback_bases,
    )
    if loaded.source == "yaml" and loaded.macros:
        REFERENCE_MACRO_CATEGORIES = loaded.macros
        _item_to_macro_cache = None
        if loaded.bases:
            REFERENCE_CATALOG = {
                base_id: list(meta.get("generators") or [])
                for base_id, meta in loaded.bases.items()
            }
            for base_id, meta in loaded.bases.items():
                if meta.get("label"):
                    BASE_LABELS[base_id] = str(meta["label"])
                entry = {
                    k: meta[k]
                    for k in ("description", "paper_title", "paper_url")
                    if meta.get(k)
                }
                if entry:
                    BASE_CATALOG[base_id] = {**BASE_CATALOG.get(base_id, {}), **entry}

    yaml_defaults = population_items(
        "synthetic_image",
        "default_modern",
        item_factory=PopulationItem,
        which="fit_items",
    )
    if yaml_defaults:
        selected = {item.key for item in yaml_defaults}
        ordered = [item for item in _default_items() if item.key in selected]
        DEFAULT_MODERN_REFERENCE = tuple(ordered or yaml_defaults)
    else:
        DEFAULT_MODERN_REFERENCE = _build_default_modern_reference()
    return loaded.source


def reference_macro_catalog() -> list[dict[str, Any]]:
    """Return hierarchical catalog: macro category -> base group -> generators."""
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
            base["generators"].append(
                {
                    "id": item.subgroup,
                    "label": item.subgroup,
                    "deploy_year": generator_deploy_year(item.subgroup),
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


def reference_population_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": base,
            "label": BASE_LABELS.get(base, base),
            "generators": [{"id": generator, "label": generator} for generator in generators],
        }
        for base, generators in REFERENCE_CATALOG.items()
    ]


def _default_items() -> list[PopulationItem]:
    return [PopulationItem(base, generator) for base, generators in REFERENCE_CATALOG.items() for generator in generators]


def _expand_macro(macro_id: str) -> list[PopulationItem]:
    macro = REFERENCE_MACRO_CATEGORIES.get(macro_id)
    return list(macro["items"]) if macro else []


def _build_default_modern_reference() -> tuple[PopulationItem, ...]:
    """Difusão Transformer + Difusão CNN moderna + AIGI Bench Social (SocialRF)."""
    by_key: dict[str, PopulationItem] = {}
    for macro_id in ("diffusion_transformer", "diffusion_cnn_modern"):
        for item in _expand_macro(macro_id):
            by_key[item.key] = item
    by_key["AIGIBench_SocialRF/SocialRF"] = PopulationItem("AIGIBench_SocialRF", "SocialRF")
    selected = set(by_key)
    ordered = [item for item in _default_items() if item.key in selected]
    return tuple(ordered or by_key.values())


def default_reference_population() -> list[dict[str, str]]:
    return [
        {"base_group": item.base_group, "subgroup": item.subgroup}
        for item in DEFAULT_MODERN_REFERENCE
    ]


# Build reverse lookup lazily so REFERENCE_MACRO_CATEGORIES can be declared
# after PopulationItem without forward-reference issues.
_item_to_macro_cache: dict[str, str] | None = None


def _item_to_macro() -> dict[str, str]:
    global _item_to_macro_cache
    if _item_to_macro_cache is None:
        _item_to_macro_cache = {
            item.key: macro_id
            for macro_id, macro in REFERENCE_MACRO_CATEGORIES.items()
            for item in macro["items"]
        }
    return _item_to_macro_cache


def get_macro_category(item: PopulationItem) -> str | None:
    """Return the macro category id for a reference population item, if any."""
    return _item_to_macro().get(item.key)


def _expand_items(raw_items: list[Any]) -> list[PopulationItem]:
    items: list[PopulationItem] = []
    for item in raw_items:
        if isinstance(item, str):
            if item.startswith("macro:"):
                items.extend(_expand_macro(item[len("macro:"):]))
            elif "/" in item:
                base, subgroup = item.split("/", 1)
                if base in REFERENCE_CATALOG and subgroup in REFERENCE_CATALOG[base]:
                    items.append(PopulationItem(base, subgroup))
        elif isinstance(item, dict):
            macro_id = str(item.get("macro") or "")
            if macro_id:
                items.extend(_expand_macro(macro_id))
                continue
            base = str(item.get("base_group") or item.get("base") or "")
            subgroup = str(item.get("subgroup") or item.get("generator") or "")
            if base in REFERENCE_CATALOG and subgroup in REFERENCE_CATALOG[base]:
                items.append(PopulationItem(base, subgroup))
    return items


def normalize_reference_selection(selection: Any) -> list[PopulationItem]:
    fallback = list(DEFAULT_MODERN_REFERENCE or _build_default_modern_reference())
    if selection is None:
        return fallback
    # Explicit empty list (used by fit_items/test_items parsers) stays empty.
    if isinstance(selection, (list, tuple)) and len(selection) == 0:
        return []

    items: list[PopulationItem] = []

    if isinstance(selection, dict):
        # Direct macro selection: {"macro": "gan_older"} or {"macros": [...]}.
        macro_ids = selection.get("macros") or []
        if isinstance(macro_ids, str):
            macro_ids = [macro_ids]
        single_macro = selection.get("macro")
        if single_macro:
            macro_ids = [single_macro, *macro_ids]
        if macro_ids:
            for macro_id in macro_ids:
                items.extend(_expand_macro(str(macro_id)))
        else:
            raw_items = selection.get("items") or selection.get("selected") or []
            if isinstance(raw_items, list):
                items.extend(_expand_items(raw_items))
    elif isinstance(selection, list):
        items.extend(_expand_items(selection))

    # Stable unique ordering according to catalog.
    selected = {item.key for item in items}
    ordered = [item for item in _default_items() if item.key in selected]
    return ordered or fallback


def normalize_reference_selection_roles(selection: Any) -> ReferenceSelectionRoles:
    """Parse fit/test subgroup selections with backward-compatible ``items`` fallback."""
    fallback = tuple(DEFAULT_MODERN_REFERENCE or _build_default_modern_reference())
    if selection is None:
        return ReferenceSelectionRoles(fallback, fallback)

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


# Load YAML macros/populations now that helpers exist.
refresh_reference_catalog_from_disk()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _logit_prob(series: pd.Series | np.ndarray, eps: float = 1e-6) -> np.ndarray:
    values = np.clip(np.asarray(series, dtype=float), eps, 1.0 - eps)
    return np.log(values / (1.0 - values))


def _load_scores(score_matrix: Path = DEFAULT_SCORE_MATRIX) -> pd.DataFrame:
    resolved = score_matrix.resolve()
    stat = resolved.stat()
    cache_key = (str(resolved), stat.st_mtime, stat.st_size)
    cached = _SCORE_MATRIX_DF_CACHE.get(cache_key)
    if cached is not None:
        return cached.copy()

    df = pd.read_csv(score_matrix, low_memory=False)
    df = df[df["error"].fillna("").eq("")].copy()
    df["y_fake"] = df["y_fake"].astype(int)
    for detector in ALL_DETECTORS:
        df[f"{detector}_logit_prob"] = _logit_prob(df[f"{detector}_fake_prob"])
    _SCORE_MATRIX_DF_CACHE[cache_key] = df.copy()
    return df


def _query_for_item(df: pd.DataFrame, item: PopulationItem, y_fake: int) -> pd.Series:
    if item.base_group == "GenImage":
        return df["dataset"].eq("GenImage") & df["generator"].eq(item.subgroup) & df["y_fake"].eq(y_fake)
    if item.base_group == "Defactify":
        if y_fake:
            return df["dataset"].eq("Defactify_MS_COCOAI") & df["generator"].eq(item.subgroup) & df["y_fake"].eq(1)
        return df["dataset"].eq("Defactify_MS_COCOAI") & df["y_fake"].eq(0)
    if item.base_group == "AIGCDetectBenchmark":
        if y_fake:
            return df["dataset"].eq("AIGCDetectBenchmark") & df["generator"].eq(item.subgroup) & df["y_fake"].eq(1)
        return df["dataset"].eq("AIGCDetectBenchmark") & df["y_fake"].eq(0)
    if item.base_group == "OpenSDI":
        if y_fake:
            return df["dataset"].eq("OpenSDI_test") & df["generator"].eq(item.subgroup) & df["y_fake"].eq(1)
        return df["dataset"].eq("OpenSDI_test") & df["y_fake"].eq(0)
    if item.base_group == "AIGIBench_no_SocialRF":
        generator = item.subgroup if y_fake else f"{item.subgroup}_real"
        return df["dataset"].eq("AIGIBench") & df["generator"].eq(generator) & df["y_fake"].eq(y_fake)
    if item.base_group == "AIGIBench_SocialRF":
        generator = "SocialRF" if y_fake else "SocialRF_real"
        return df["dataset"].eq("AIGIBench") & df["generator"].eq(generator) & df["y_fake"].eq(y_fake)
    if item.base_group == "Synthbuster":
        if y_fake:
            return df["dataset"].eq("Synthbuster") & df["generator"].eq(item.subgroup) & df["y_fake"].eq(1)
        return df["dataset"].eq("Synthbuster") & df["generator"].eq("RAISE") & df["y_fake"].eq(0)
    if item.base_group == "BFree_extended_synthbuster":
        if y_fake:
            return df["dataset"].eq("BFree_extended_synthbuster") & df["generator"].eq(item.subgroup) & df["y_fake"].eq(1)
        return df["dataset"].eq("BFree_extended_synthbuster") & df["generator"].eq("RAISE") & df["y_fake"].eq(0)
    # Generic ingested bases: UI base_group == CSV dataset, GenImage-style subgroup×class.
    dataset_name = _dataset_name_for_base_group(item.base_group)
    return (
        df["dataset"].astype(str).eq(dataset_name)
        & df["generator"].astype(str).eq(item.subgroup)
        & df["y_fake"].astype(int).eq(int(y_fake))
    )


def _dataset_name_for_base_group(base_group: str) -> str:
    """Map UI base_group → score-matrix ``dataset`` column (1:1 for new ingestions)."""
    known = {
        "GenImage": "GenImage",
        "Defactify": "Defactify_MS_COCOAI",
        "AIGCDetectBenchmark": "AIGCDetectBenchmark",
        "OpenSDI": "OpenSDI_test",
        "AIGIBench_no_SocialRF": "AIGIBench",
        "AIGIBench_SocialRF": "AIGIBench",
        "Synthbuster": "Synthbuster",
        "BFree_extended_synthbuster": "BFree_extended_synthbuster",
    }
    return known.get(base_group, base_group)


def _sample_rows(df: pd.DataFrame, n: int, rng: np.random.Generator, context: str) -> pd.DataFrame:
    if len(df) >= n:
        return df.sample(n=n, random_state=int(rng.integers(0, 2**31 - 1))).copy()
    # Small population: sample with replacement so the pipeline can still be trained.
    return df.sample(n=n, replace=True, random_state=int(rng.integers(0, 2**31 - 1))).copy()


def _filter_matrix_scope(df: pd.DataFrame, *, augmented_reference: bool) -> pd.DataFrame:
    """Keep only original rows unless augmented reference is requested."""
    if "augmentation" not in df.columns:
        return df.copy()
    aug = df["augmentation"].fillna("").astype(str)
    if augmented_reference:
        return df.copy()
    return df[aug.isin(("", ORIGINAL_AUGMENTATION_TAG))].copy()


def _item_has_fake_candidates(df: pd.DataFrame, item: PopulationItem) -> bool:
    try:
        return bool(_query_for_item(df, item, 1).any())
    except Exception:
        return False


def _resolve_scope_for_population(
    df: pd.DataFrame,
    items: list[PopulationItem],
    *,
    augmented_reference: bool,
    sample_multiplier: int,
) -> tuple[pd.DataFrame, bool, int, list[str]]:
    """Apply originals/augmented filter; auto-promote to augmented when needed.

    Some published representation matrices (notably AIGCDetectBenchmark) only
    contain augmented fakes. Tipicidade latente lê esse CSV e, com
    ``augmented_reference=False``, ficava sem candidatos → erro opaco.
    """
    scoped = _filter_matrix_scope(df, augmented_reference=augmented_reference)
    missing = [item.key for item in items if not _item_has_fake_candidates(scoped, item)]
    if not missing:
        return scoped, augmented_reference, sample_multiplier, []

    if augmented_reference:
        raise RuntimeError(
            "LR por população de referência: nenhum candidato fake para "
            + ", ".join(missing)
            + " na matriz de scores/representations carregada."
        )

    aug_scoped = _filter_matrix_scope(df, augmented_reference=True)
    still_missing = [
        item.key for item in items if not _item_has_fake_candidates(aug_scoped, item)
    ]
    if still_missing:
        raise RuntimeError(
            "LR por população de referência: nenhum candidato fake para "
            + ", ".join(still_missing)
            + ". Verifique se a população existe na matriz publicada "
            "(reference_data/.../scores ou representations)."
        )

    # Originais ausentes, mas aumentados existem → promove automaticamente.
    return (
        aug_scoped,
        True,
        max(int(sample_multiplier), int(AUGMENTATION_MULTIPLIER)),
        missing,
    )


def _augmentation_strata(df: pd.DataFrame) -> pd.Series:
    """Return a categorical series: '' for originals, otherwise augmentation name."""
    if "augmentation" in df.columns:
        return df["augmentation"].fillna("").astype(str)
    return pd.Series("", index=df.index)


def _sample_stratified(
    candidates: pd.DataFrame,
    n_total: int,
    rng: np.random.Generator,
    context: str,
) -> pd.DataFrame:
    """Sample n_total rows from candidates, spreading equally across augmentation strata.

    Falls back to sampling with replacement when a stratum is too small.
    """
    if candidates.empty:
        if n_total == 0:
            return candidates.copy()
        raise RuntimeError(
            f"{context}: nenhum candidato disponivel "
            "(verifique se a população existe na matriz e se "
            "referência aumentada / tipicidade latente batem com os dados publicados)"
        )

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


def _build_reference_sample(
    df: pd.DataFrame,
    items: list[PopulationItem],
    seed: int,
    sample_multiplier: int = 1,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    real_pool_offsets: dict[str, int] = {}
    real_pools: dict[str, pd.DataFrame] = {}
    frames: list[pd.DataFrame] = []

    sample_per_class = SAMPLE_PER_CLASS * max(1, sample_multiplier)

    # Bases where all generators share a single real pool.
    POOL_BASES = {"Defactify", "AIGCDetectBenchmark", "OpenSDI", "Synthbuster", "BFree_extended_synthbuster"}
    base_counts: dict[str, int] = {}
    for item in items:
        base_counts[item.base_group] = base_counts.get(item.base_group, 0) + 1

    def _sample_with_fallback(candidates: pd.DataFrame, n: int, context: str) -> pd.DataFrame:
        if "augmentation" in candidates.columns:
            return _sample_stratified(candidates, n, rng, context)
        if len(candidates) >= n:
            return candidates.sample(n=n, random_state=int(rng.integers(0, 2**31 - 1))).copy()
        # Not enough real images: sample with replacement so the model can still be trained.
        return candidates.sample(n=n, replace=True, random_state=int(rng.integers(0, 2**31 - 1))).copy()

    for item in items:
        fake_candidates = df[_query_for_item(df, item, 1)]
        fake = _sample_with_fallback(fake_candidates, sample_per_class, f"{item.key}/fake")

        real_query = _query_for_item(df, item, 0)
        real_candidates = df[real_query]
        uses_pool = item.base_group in POOL_BASES
        if uses_pool:
            if item.base_group not in real_pools:
                needed = base_counts[item.base_group] * sample_per_class
                real_pools[item.base_group] = _sample_with_fallback(
                    real_candidates, max(needed, len(real_candidates)), f"{item.base_group}/pool"
                ).reset_index(drop=True)
                real_pool_offsets[item.base_group] = 0
            start = real_pool_offsets[item.base_group]
            end = start + sample_per_class
            pool = real_pools[item.base_group]
            if end > len(pool):
                # Fallback: wrap around / resample from the pool with replacement.
                indices = (np.arange(start, end) % len(pool)).tolist()
                real = pool.iloc[indices].copy()
            else:
                real = pool.iloc[start:end].copy()
            real_pool_offsets[item.base_group] = end
        else:
            real = _sample_with_fallback(real_candidates, sample_per_class, f"{item.key}/real")

        for frame in (real, fake):
            frame["reference_base_group"] = item.base_group
            frame["reference_subgroup"] = item.subgroup
            frame["reference_key"] = item.key
        frames.extend([real, fake])

    sample = pd.concat(frames, ignore_index=True)
    for (key, y_fake), group in sample.groupby(["reference_key", "y_fake"]):
        if len(group) != sample_per_class:
            raise RuntimeError(f"Amostra invalida para {key}/y_fake={y_fake}: {len(group)} (esperado {sample_per_class})")
    return sample


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


def _eer(y_real: np.ndarray, scores: np.ndarray) -> float:
    fpr, tpr, _ = roc_curve(y_real, scores)
    fnr = 1.0 - tpr
    idx = int(np.nanargmin(np.abs(fnr - fpr)))
    return float((fpr[idx] + fnr[idx]) / 2.0)


def _cllr_ln(ln_lr_real: np.ndarray, y_real: np.ndarray) -> float:
    target = ln_lr_real[y_real == 1]
    nontarget = ln_lr_real[y_real == 0]
    if len(target) == 0 or len(nontarget) == 0:
        return float("nan")
    c_target = np.logaddexp(0.0, -target) / math.log(2.0)
    c_non = np.logaddexp(0.0, nontarget) / math.log(2.0)
    return float(0.5 * (np.mean(c_target) + np.mean(c_non)))


def _min_cllr_ln(ln_lr_real: np.ndarray, y_real: np.ndarray) -> float:
    if len(set(y_real.tolist())) < 2:
        return float("nan")
    order = np.argsort(ln_lr_real)
    iso = IsotonicRegression(out_of_bounds="clip")
    calibrated = iso.fit_transform(ln_lr_real[order], y_real[order])
    restored = np.empty_like(calibrated, dtype=float)
    restored[order] = calibrated
    p = np.clip(restored, 1e-6, 1.0 - 1e-6)
    return _cllr_ln(np.log(p / (1.0 - p)), y_real)


def _metrics(df: pd.DataFrame) -> dict[str, Any]:
    y_real = (1 - df["y_fake"].astype(int)).to_numpy()
    ln_lr = df["ln_lr_real"].to_numpy(dtype=float)
    return {
        "rows": int(len(df)),
        "real_rows": int(np.sum(y_real == 1)),
        "fake_rows": int(np.sum(y_real == 0)),
        "cllr": _cllr_ln(ln_lr, y_real),
        "min_cllr": _min_cllr_ln(ln_lr, y_real),
        "auc": float(roc_auc_score(y_real, ln_lr)) if len(set(y_real.tolist())) == 2 else float("nan"),
        "eer": _eer(y_real, ln_lr) if len(set(y_real.tolist())) == 2 else float("nan"),
        "wrong_extreme_lr_count": int(
            np.sum(((y_real == 1) & (ln_lr < -2 * math.log(10.0))) | ((y_real == 0) & (ln_lr > 2 * math.log(10.0))))
        ),
    }


def _classifier_label(name: str) -> str:
    return _CLASSIFIER_LABELS.get(name, name)


def _validate_classifier(classifier: str) -> str:
    classifier = (classifier or DEFAULT_META_CLASSIFIER).lower().strip()
    classifier = _CLASSIFIER_ALIASES.get(classifier, classifier)
    if classifier not in META_CLASSIFIERS:
        raise RuntimeError(
            f"Classificador meta '{classifier}' nao suportado. "
            f"Use um de: {', '.join(META_CLASSIFIERS)}"
        )
    return classifier


def normalize_meta_classifier(classifier: str | None = None) -> str:
    """Canonical meta-classifier id (logistic | xgboost); accepts legacy aliases."""
    return _validate_classifier(classifier or DEFAULT_META_CLASSIFIER)


def _train_meta_classifier(
    classifier: str,
    x: np.ndarray,
    y: np.ndarray,
    feature_cols: list[str],
    seed: int,
) -> Any:
    """Train a meta-classifier on detector logit features (logistic | xgboost)."""
    del feature_cols  # reserved for future per-feature options
    classifier = _validate_classifier(classifier)
    if classifier == "logistic":
        model: Any = LogisticRegression(C=1.0, max_iter=2000, solver="lbfgs", random_state=seed)
    elif classifier == "xgboost":
        model = XGBClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.1,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=seed,
            n_jobs=4,
            verbosity=0,
        )
    else:
        raise RuntimeError(f"Classificador nao implementado: {classifier}")
    model.fit(x, y)
    return model


def _classifier_decision_scores(model: Any, x: np.ndarray) -> np.ndarray:
    """Return a real-valued score in the direction real > synthetic.

    Prefer decision_function when present (LogisticRegression linear score).
    Otherwise use logit(p_real) from predict_proba (XGBoost).
    """
    if hasattr(model, "decision_function"):
        return np.asarray(model.decision_function(x), dtype=float)
    proba = np.asarray(model.predict_proba(x), dtype=float)
    p_real = np.clip(proba[:, 1], 1e-6, 1.0 - 1e-6)
    return _logit_prob(p_real)


def _classifier_feature_importance(model: Any, feature_cols: list[str]) -> dict[str, float] | None:
    """Return logistic coefficients or XGBoost feature importances when available."""
    if hasattr(model, "coef_"):
        return dict(zip(feature_cols, np.asarray(model.coef_[0], dtype=float).tolist()))
    if hasattr(model, "feature_importances_"):
        return dict(zip(feature_cols, np.asarray(model.feature_importances_, dtype=float).tolist()))
    return None


def _fit_bigauss(split: pd.DataFrame, model: Any, feature_cols: list[str]) -> dict[str, Any]:
    calib = split[split["reference_split"].eq("calibration_bigauss")]
    x = calib[feature_cols].to_numpy(dtype=float)
    y_real = (1 - calib["y_fake"].astype(int)).to_numpy()
    z = _classifier_decision_scores(model, x).astype(float)

    eer = _eer(y_real, z)
    sigma = float(-2.0 * norm.ppf(float(np.clip(eer, 1e-6, 0.499999))))
    mu_fake = -sigma**2 / 2.0
    mu_real = sigma**2 / 2.0

    order = np.argsort(z)
    z_sorted = z[order]
    y_sorted = y_real[order]
    n_fake = int(np.sum(y_real == 0))
    n_real = int(np.sum(y_real == 1))
    weights = np.where(y_sorted == 1, 1.0 / (2.0 * (n_real + 1)), 1.0 / (2.0 * (n_fake + 1)))
    cdf = np.cumsum(weights)
    unique_z = np.unique(z_sorted)
    last_idx = np.array([np.where(z_sorted == value)[0][-1] for value in unique_z], dtype=int)
    cdf_unique = cdf[last_idx]

    empirical_cdf = interp1d(
        unique_z,
        cdf_unique,
        kind="linear",
        bounds_error=False,
        fill_value=(float(cdf_unique[0]), float(cdf_unique[-1])),
        assume_sorted=True,
    )
    y_min = mu_fake - 12.0 * sigma
    y_max = mu_real + 12.0 * sigma

    def mix_cdf(value: float) -> float:
        return float(0.5 * norm.cdf(value, mu_fake, sigma) + 0.5 * norm.cdf(value, mu_real, sigma))

    def inv_cdf(prob: float) -> float:
        p = float(np.clip(prob, float(cdf_unique[0]), float(cdf_unique[-1])))
        return float(brentq(lambda value: mix_cdf(value) - p, y_min, y_max, maxiter=100))

    return {
        "eer": float(eer),
        "sigma": sigma,
        "mu_fake": float(mu_fake),
        "mu_real": float(mu_real),
        "z_values": unique_z.astype(float),
        "cdf_values": cdf_unique.astype(float),
        "empirical_cdf": empirical_cdf,
        "inv_cdf": np.vectorize(inv_cdf),
    }


def _apply(model: Any, calibration: dict[str, Any], features: np.ndarray) -> dict[str, float]:
    z = float(_classifier_decision_scores(model, features.reshape(1, -1))[0])
    p = float(calibration["empirical_cdf"]([z])[0])
    ln_lr = float(calibration["inv_cdf"]([p])[0])
    return {
        "logreg_z": z,
        "cdf_p": p,
        "ln_lr": ln_lr,
        "log10_lr": ln_lr / math.log(10.0),
        "lr": float(math.exp(float(np.clip(ln_lr, -700, 700)))),
    }


def _score_dataframe(
    split: pd.DataFrame,
    model: Any,
    calibration: dict[str, Any],
    feature_cols: list[str],
) -> pd.DataFrame:
    scored = split.copy()
    x = scored[feature_cols].to_numpy(dtype=float)
    z = _classifier_decision_scores(model, x).astype(float)
    p = calibration["empirical_cdf"](z).astype(float)
    ln_lr = calibration["inv_cdf"](p).astype(float)
    scored["logreg_z_real"] = z
    scored["bigauss_cdf_p"] = p
    scored["ln_lr_real"] = ln_lr
    scored["log10_lr_real"] = ln_lr / math.log(10.0)
    scored["lr_real"] = np.exp(np.clip(ln_lr, -700, 700))
    return scored


def _safe_kde(values: np.ndarray) -> gaussian_kde:
    if len(np.unique(values)) < 2:
        values = values + np.linspace(-1e-6, 1e-6, len(values))
    return gaussian_kde(values)


def _plot_tippett(path: Path, df: pd.DataFrame, title: str) -> None:
    plt.figure(figsize=(8, 5))
    fake_values = np.sort(df.loc[df["y_fake"].eq(1), "log10_lr_real"].to_numpy(dtype=float))
    real_values = np.sort(df.loc[df["y_fake"].eq(0), "log10_lr_real"].to_numpy(dtype=float))
    if len(fake_values):
        fake_survival = 1.0 - np.arange(0, len(fake_values)) / len(fake_values)
        plt.step(fake_values, fake_survival, where="post", label="H0 sintética: proporção >= x", color="red")
    if len(real_values):
        real_cdf = np.arange(1, len(real_values) + 1) / len(real_values)
        plt.step(real_values, real_cdf, where="post", label="H1 real: proporção <= x", color="blue")
    plt.axvline(0, color="black", linewidth=1, linestyle="--")
    plt.xlabel("log10 LR (positivo favorece real)")
    plt.ylabel("Proporção acumulada")
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def _plot_distribution(path: Path, df: pd.DataFrame, title: str, questioned_log10_lr: float | None = None) -> None:
    fake = df.loc[df["y_fake"].eq(1), "log10_lr_real"].to_numpy(dtype=float)
    real = df.loc[df["y_fake"].eq(0), "log10_lr_real"].to_numpy(dtype=float)
    values = np.concatenate([fake, real])
    bins = np.linspace(float(np.nanmin(values)), float(np.nanmax(values)), 40)
    plt.figure(figsize=(8, 5))
    plt.hist(fake, bins=bins, alpha=0.6, label="sintética", color="red")
    plt.hist(real, bins=bins, alpha=0.6, label="real", color="blue")
    plt.axvline(0, color="black", linewidth=1, linestyle="--")
    if questioned_log10_lr is not None and np.isfinite(questioned_log10_lr):
        plt.axvline(questioned_log10_lr, color="red", linewidth=2, linestyle="--", label="LR da evidência")
    plt.xlabel("log10 LR (positivo favorece real)")
    plt.ylabel("contagem")
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def _plot_identity(path: Path, df: pd.DataFrame, title: str) -> float:
    fake = df.loc[df["y_fake"].eq(1), "ln_lr_real"].to_numpy(dtype=float)
    real = df.loc[df["y_fake"].eq(0), "ln_lr_real"].to_numpy(dtype=float)
    values = np.concatenate([fake, real])
    lo, hi = float(np.percentile(values, 1)), float(np.percentile(values, 99))
    grid = np.linspace(lo, hi, 500)
    density_fake = np.maximum(_safe_kde(fake)(grid), 1e-300)
    density_real = np.maximum(_safe_kde(real)(grid), 1e-300)
    log_ratio = np.log(density_real / density_fake)
    mse = float(np.mean((log_ratio - grid) ** 2))
    plt.figure(figsize=(6, 6))
    plt.plot(grid, log_ratio, label="ln[p(lnLR|real)/p(lnLR|sintética)]")
    plt.plot(grid, grid, linestyle="--", label="identidade")
    plt.xlabel("ln LR real")
    plt.ylabel("log-razão de densidades")
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()
    return mse


def _detector_features(detector_scores: dict[str, Any], selected_detectors: tuple[str, ...]) -> np.ndarray:
    missing = [detector for detector in selected_detectors if detector not in detector_scores]
    if missing:
        raise RuntimeError("LR exige os detectores selecionados. Ausentes: " + ", ".join(missing))
    return np.array(
        [_logit_prob([float(detector_scores[detector]["fake_prob"])])[0] for detector in selected_detectors],
        dtype=float,
    )


def _feature_cols(selected_detectors: tuple[str, ...]) -> list[str]:
    return [FEATURE_COLS_FOR_DETECTORS[detector] for detector in selected_detectors]


def _filter_rows_with_embeddings(
    df: pd.DataFrame,
    selected_detectors: tuple[str, ...],
) -> pd.DataFrame:
    """Drop rows that are missing any required embedding path or .npy file."""
    if row_has_embeddings is None:
        raise RuntimeError("latent_typicality module not available")
    mask = pd.Series(True, index=df.index)
    for detector in selected_detectors:
        mask &= df[f"{detector}_embedding_path"].notna()
    df = df[mask].copy()
    present = df.apply(
        lambda row: row_has_embeddings(row, selected_detectors),
        axis=1,
    )
    return df[present].copy()


def _load_embedding_stack(df: pd.DataFrame, detector: str) -> np.ndarray:
    """Load all embeddings for ``detector`` as a single (N, D) float32 array."""
    paths = df[f"{detector}_embedding_path"].astype(str).tolist()
    if resolve_embedding_path is not None:
        embeddings = [np.load(str(resolve_embedding_path(p))) for p in paths]
    else:
        embeddings = [np.load(p) for p in paths]
    return np.stack(embeddings, axis=0).astype(np.float32)


def _build_typicality_refs(
    train_df: pd.DataFrame,
    selected_detectors: tuple[str, ...],
    typicality_k: int,
    typicality_distance: str,
) -> dict[str, TypicalityReference]:
    """Build k-NN typicality references on the train split (anti-leak)."""
    if build_typicality_reference is None:
        raise RuntimeError("latent_typicality module not available")
    refs: dict[str, TypicalityReference] = {}
    for detector in selected_detectors:
        real_df = train_df[train_df["y_fake"].eq(0)]
        spoof_df = train_df[train_df["y_fake"].eq(1)]
        real_emb = _load_embedding_stack(real_df, detector)
        spoof_emb = _load_embedding_stack(spoof_df, detector)
        refs[detector] = build_typicality_reference(
            detector=detector,
            distance=typicality_distance,  # type: ignore[arg-type]
            k=typicality_k,
            real_embeddings=real_emb,
            synthetic_embeddings=spoof_emb,
            real_ids=[str(r.get("sample_id", idx)) for idx, r in real_df.iterrows()],
            synthetic_ids=[str(r.get("sample_id", idx)) for idx, r in spoof_df.iterrows()],
        )
    return refs


def _materialize_typicality_features(
    df: pd.DataFrame,
    typicality_refs: dict[str, TypicalityReference],
    selected_detectors: tuple[str, ...],
) -> pd.DataFrame:
    """Add score + typicality feature columns to ``df`` and return it."""
    if typicality_features_batch is None:
        raise RuntimeError("latent_typicality module not available")
    for detector in selected_detectors:
        df[f"S_{detector}"] = df[f"{detector}_logit_prob"].to_numpy(dtype=float)
        embeddings = _load_embedding_stack(df, detector)
        # exclude_self only makes sense for the train split; for calib/test the
        # query point is not part of the reference bank.
        exclude_self = df["reference_split"].eq("train_logreg").to_numpy()
        features = typicality_features_batch(
            embeddings=embeddings,
            ref=typicality_refs[detector],
            exclude_self=exclude_self,
        )
        for col, values in features.items():
            df[col] = values
    return df


def _build_questioned_features(
    detector_scores: dict[str, Any],
    selected_detectors: tuple[str, ...],
    typicality_refs: dict[str, TypicalityReference],
    typicality_system: str = DEFAULT_TYPICALITY_SYSTEM,
) -> np.ndarray:
    """Build the feature vector for the questioned evidence.

    For latent typicality this requires each selected detector to provide an
    ``embedding`` alongside its ``fake_prob``.
    """
    if typicality_features_batch is None:
        raise RuntimeError("latent_typicality module not available")
    feature_dict: dict[str, float] = {}
    for detector in selected_detectors:
        scores = detector_scores.get(detector) or {}
        embedding = scores.get("embedding")
        if embedding is None:
            raise RuntimeError(
                f"Embedding ausente para detector {detector}; "
                "tipicidade latente requer return_embedding=True"
            )
        emb = np.asarray(embedding, dtype=np.float32).reshape(1, -1)
        features = typicality_features_batch(
            embeddings=emb,
            ref=typicality_refs[detector],
        )
        for col, values in features.items():
            feature_dict[col] = float(values[0])
        feature_dict[f"S_{detector}"] = float(_logit_prob([float(scores["fake_prob"])])[0])
    col_order = feature_columns_for_detectors(typicality_system, selected_detectors)
    return np.array([feature_dict[col] for col in col_order], dtype=float)


def _write_summary_txt(path: Path, report: dict[str, Any]) -> None:
    q = report.get("questioned", {})
    metrics = report.get("test_metrics", {})
    items = report.get("selected_items", [])
    feature_weights = report.get("feature_weights", {})
    classifier_label = report.get("meta_classifier_label", _CLASSIFIER_LABELS.get(DEFAULT_META_CLASSIFIER))
    lines: list[str] = [
        "RELATORIO DE CALIBRACAO LR - POPULACAO DE REFERENCIA",
        "=" * 60,
        "",
        f"Hipese positiva (H1): {report.get('hypothesis_positive', 'real_authentic')}",
        f"Hipese negativa (H0): {report.get('hypothesis_negative', 'synthetic_ai_generated')}",
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
        f"Imagens  = {metrics.get('rows', '—')} (real={metrics.get('real_rows', '—')}, sintetica={metrics.get('fake_rows', '—')})",
        "",
        "POPULACAO SELECIONADA",
        "-" * 60,
        f"Subgrupos: {report.get('selected_count', '—')}",
        f"Amostras por classe/subgrupo: {report.get('sample_per_class_per_subgroup', '—')}",
    ]
    if report.get("augmented_reference"):
        lines.extend([
            f"Referencia aumentada: sim (multiplicador={report.get('sample_multiplier', '—')})",
            f"Augmentacoes: {', '.join(AUGMENTATION_NAMES)}",
        ])
    else:
        lines.append("Referencia aumentada: nao (somente originais)")
    if report.get("use_latent_typicality"):
        lines.append(
            f"Tipicidade latente: sim (sistema={report.get('typicality_system', '—')}, "
            f"k={report.get('typicality_k', '—')}, distancia={report.get('typicality_distance', '—')})"
        )
    for item in items:
        lines.append(f"  - {item.get('base_group', '')} / {item.get('subgroup', '')}")
    if feature_weights:
        lines.extend([
            "",
            "PESOS / IMPORTANCIA DOS DETECTORES",
            "-" * 60,
        ])
        for name, value in feature_weights.items():
            lines.append(f"  {name} = {value}")
    if report.get("logreg_intercept") is not None:
        lines.append(f"  intercepto = {report.get('logreg_intercept')}")
    lines.extend([
        "",
        "NOTA",
        "-" * 60,
        report.get("note", "LR > 1 favorece H1=real/autentica; LR < 1 favorece H0=sintetica/gerada por IA."),
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def _cache_dir() -> Path:
    return _reference_lr_cache_dir()


# Opaque content hashes of synthetic representations.csv from earlier on-disk
# layouts. Kept so existing joblib caches remain addressable after path moves
# inside reference_data/.
_LEGACY_REPS_MATRIX_HASHES: tuple[str, ...] = (
    "791a84597ebe3de1",
    "c932672d60cbbae0",
    "30ea2e6208d3a316",
)


def _normalize_matrix_text_for_hash(text: str) -> str:
    """Collapse absolute ``reference_data`` prefixes before hashing CSVs."""
    import re

    patterns = (
        (
            r"(?:[A-Za-z]:)?(?:/[^,\n\"]+)?/reference_data/synthetic_image/features/representations/",
            "<SYN_REPS>/",
        ),
        (
            r"(?:[A-Za-z]:)?(?:/[^,\n\"]+)?/reference_data/synthetic_image/",
            "<SYN_IMG>/",
        ),
        (
            r"(?:[A-Za-z]:)?(?:/[^,\n\"]+)?/reference_data/audio_spoofing/",
            "<AUDIO_REF>/",
        ),
        (
            r"(?:[A-Za-z]:)?(?:/[^,\n\"]+)?/reference_data/",
            "<REFDATA>/",
        ),
    )
    normalized = text
    for pattern, repl in patterns:
        normalized = re.sub(pattern, repl, normalized)
    return normalized


def _raw_file_hash(score_matrix: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(score_matrix, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _matrix_hash_sidecar_path(score_matrix: Path) -> Path:
    return score_matrix.with_suffix(score_matrix.suffix + ".sha16")


def _score_matrix_hash(score_matrix: Path) -> str:
    """Content hash stable across reference_data path-prefix migrations.

    Result is cached next to the matrix (``.sha16``) keyed by size+mtime so HIT
    paths do not re-read multi‑hundred‑MB CSVs on every job.
    """
    import hashlib
    import json

    path = Path(score_matrix)
    stat = path.stat()
    sidecar = _matrix_hash_sidecar_path(path)
    token = f"{stat.st_size}:{stat.st_mtime_ns}"
    if sidecar.is_file():
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            if payload.get("token") == token and payload.get("hash"):
                return str(payload["hash"])
        except Exception:
            pass

    raw = path.read_bytes()
    try:
        normalized = _normalize_matrix_text_for_hash(raw.decode("utf-8")).encode("utf-8")
    except UnicodeDecodeError:
        normalized = raw
    digest = hashlib.sha256(normalized).hexdigest()[:16]
    try:
        sidecar.write_text(
            json.dumps({"token": token, "hash": digest}, sort_keys=True),
            encoding="utf-8",
        )
    except OSError:
        pass
    return digest


def _macro_category_for_selection(selection: Any) -> str | None:
    """Return macro category id if selection matches exactly one macro category."""
    roles = normalize_reference_selection_roles(selection)
    if roles.fit_keys != roles.test_keys:
        return None
    item_set = set(roles.fit_keys)
    for macro_id, macro in REFERENCE_MACRO_CATEGORIES.items():
        macro_set = {item.key for item in macro["items"]}
        if item_set == macro_set:
            return macro_id
    return None


def _cache_key_from_parts(
    *,
    score_matrix_hash: str,
    macro_category: str | None,
    items: list[PopulationItem],
    selected_detectors: tuple[str, ...],
    classifier: str,
    seed: int,
    sample_multiplier: int = 1,
    use_latent_typicality: bool = False,
    typicality_system: str = DEFAULT_TYPICALITY_SYSTEM,
    typicality_k: int = DEFAULT_TYPICALITY_K,
    typicality_distance: str = DEFAULT_TYPICALITY_DISTANCE,
    fit_items: list[PopulationItem] | None = None,
    test_items: list[PopulationItem] | None = None,
) -> str:
    import hashlib

    fit = list(fit_items) if fit_items is not None else list(items)
    test = list(test_items) if test_items is not None else list(items)
    roles_separated = {item.key for item in fit} != {item.key for item in test}

    canonical: dict[str, Any] = {
        "score_matrix_hash": score_matrix_hash,
        "macro_category": macro_category,
        # Keep legacy ``items`` key when fit==test so existing caches remain valid.
        "items": (
            sorted(item.key for item in items)
            if macro_category is None and not roles_separated
            else []
        ),
        "selected_detectors": list(selected_detectors),
        "classifier": classifier,
        "seed": seed,
        "sample_multiplier": sample_multiplier,
        "sample_per_class": SAMPLE_PER_CLASS,
    }
    if roles_separated:
        canonical["fit_items"] = sorted(item.key for item in fit)
        canonical["test_items"] = sorted(item.key for item in test)
    if use_latent_typicality:
        canonical.update(
            {
                "use_latent_typicality": True,
                "typicality_system": typicality_system,
                "typicality_k": typicality_k,
                "typicality_distance": typicality_distance,
            }
        )
    payload = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _cache_key(
    *,
    score_matrix: Path,
    macro_category: str | None,
    items: list[PopulationItem],
    selected_detectors: tuple[str, ...],
    classifier: str,
    seed: int,
    sample_multiplier: int = 1,
    use_latent_typicality: bool = False,
    typicality_system: str = DEFAULT_TYPICALITY_SYSTEM,
    typicality_k: int = DEFAULT_TYPICALITY_K,
    typicality_distance: str = DEFAULT_TYPICALITY_DISTANCE,
) -> str:
    return _cache_key_from_parts(
        score_matrix_hash=_score_matrix_hash(score_matrix),
        macro_category=macro_category,
        items=items,
        selected_detectors=selected_detectors,
        classifier=classifier,
        seed=seed,
        sample_multiplier=sample_multiplier,
        use_latent_typicality=use_latent_typicality,
        typicality_system=typicality_system,
        typicality_k=typicality_k,
        typicality_distance=typicality_distance,
    )


def _cache_key_candidates(
    *,
    score_matrix: Path,
    macro_category: str | None,
    items: list[PopulationItem],
    selected_detectors: tuple[str, ...],
    classifier: str,
    seed: int,
    sample_multiplier: int = 1,
    use_latent_typicality: bool = False,
    typicality_system: str = DEFAULT_TYPICALITY_SYSTEM,
    typicality_k: int = DEFAULT_TYPICALITY_K,
    typicality_distance: str = DEFAULT_TYPICALITY_DISTANCE,
) -> list[str]:
    """Primary path-stable hash; raw/legacy hashes only if primary cache is missing."""
    primary = _cache_key_from_parts(
        score_matrix_hash=_score_matrix_hash(score_matrix),
        macro_category=macro_category,
        items=items,
        selected_detectors=selected_detectors,
        classifier=classifier,
        seed=seed,
        sample_multiplier=sample_multiplier,
        use_latent_typicality=use_latent_typicality,
        typicality_system=typicality_system,
        typicality_k=typicality_k,
        typicality_distance=typicality_distance,
    )
    keys = [primary]
    primary_path = _cache_dir() / f"{primary}.joblib"
    if primary_path.is_file() and primary_path.stat().st_size >= 1024:
        return keys

    hashes: list[str] = [_raw_file_hash(score_matrix)]
    if use_latent_typicality:
        hashes.extend(_LEGACY_REPS_MATRIX_HASHES)
    seen = {primary}
    for matrix_hash in hashes:
        key = _cache_key_from_parts(
            score_matrix_hash=matrix_hash,
            macro_category=macro_category,
            items=items,
            selected_detectors=selected_detectors,
            classifier=classifier,
            seed=seed,
            sample_multiplier=sample_multiplier,
            use_latent_typicality=use_latent_typicality,
            typicality_system=typicality_system,
            typicality_k=typicality_k,
            typicality_distance=typicality_distance,
        )
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def _alias_lr_cache(primary_key: str, existing_key: str) -> None:
    """Point the primary cache name at an existing legacy joblib (symlink/copy)."""
    if primary_key == existing_key:
        return
    cache_dir = _cache_dir()
    primary = cache_dir / f"{primary_key}.joblib"
    existing = cache_dir / f"{existing_key}.joblib"
    if primary.exists() or not existing.is_file():
        return
    try:
        primary.symlink_to(existing.name)
    except OSError:
        import shutil

        shutil.copy2(existing, primary)


def _serialize_calibration(calibration: dict[str, Any]) -> dict[str, Any]:
    return {
        "eer": calibration["eer"],
        "sigma": calibration["sigma"],
        "mu_fake": calibration["mu_fake"],
        "mu_real": calibration["mu_real"],
        "z_values": calibration["z_values"].astype(float).tolist(),
        "cdf_values": calibration["cdf_values"].astype(float).tolist(),
    }


def _deserialize_calibration(serialized: dict[str, Any]) -> dict[str, Any]:
    """Rebuild empirical_cdf and inv_cdf from serialized values."""
    import numpy as np

    eer = float(serialized["eer"])
    sigma = float(serialized["sigma"])
    mu_fake = float(serialized["mu_fake"])
    mu_real = float(serialized["mu_real"])
    z_values = np.asarray(serialized["z_values"], dtype=float)
    cdf_values = np.asarray(serialized["cdf_values"], dtype=float)

    def mix_cdf(value: float) -> float:
        return float(0.5 * norm.cdf(value, mu_fake, sigma) + 0.5 * norm.cdf(value, mu_real, sigma))

    y_min = mu_fake - 12.0 * sigma
    y_max = mu_real + 12.0 * sigma

    def inv_cdf(prob: float) -> float:
        p = float(np.clip(prob, float(cdf_values[0]), float(cdf_values[-1])))
        return float(brentq(lambda value: mix_cdf(value) - p, y_min, y_max, maxiter=100))

    empirical_cdf = interp1d(
        z_values,
        cdf_values,
        kind="linear",
        bounds_error=False,
        fill_value=(float(cdf_values[0]), float(cdf_values[-1])),
        assume_sorted=True,
    )

    return {
        "eer": eer,
        "sigma": sigma,
        "mu_fake": mu_fake,
        "mu_real": mu_real,
        "z_values": z_values,
        "cdf_values": cdf_values,
        "empirical_cdf": empirical_cdf,
        "inv_cdf": np.vectorize(inv_cdf),
    }


def _save_lr_cache(
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
    from core.latent_typicality.typicality import slim_typicality_refs

    path = _cache_dir() / f"{cache_key}.joblib"
    payload = {
        "model": model,
        "feature_cols": feature_cols,
        "calibration": _serialize_calibration(calibration),
        "selected_detectors": list(selected_detectors),
        "metadata": metadata,
    }
    if scored is not None:
        payload["scored"] = scored
    slim_refs = slim_typicality_refs(typicality_refs)
    if slim_refs is not None:
        payload["typicality_refs"] = slim_refs
    # compress=3: tipicidade slim ~200MB → bem menor no disco e no HIT.
    joblib.dump(payload, path, compress=3)
    if scored is not None:
        _LR_SCORED_CACHE[cache_key] = scored.copy()
    return path


def _load_lr_cache(
    cache_key: str,
) -> tuple[Any, dict[str, Any], list[str], tuple[str, ...], pd.DataFrame | None, dict[str, TypicalityReference] | None] | None:
    from core.latent_typicality.typicality import rehydrate_typicality_refs

    if cache_key in _LR_SCORED_CACHE:
        scored = _LR_SCORED_CACHE[cache_key]
    else:
        scored = None

    path = _cache_dir() / f"{cache_key}.joblib"
    if not path.is_file():
        if scored is not None:
            return None, None, [], (), scored, None
        return None
    try:
        data = joblib.load(path)
        model = data["model"]
        feature_cols = list(data["feature_cols"])
        calibration = _deserialize_calibration(data["calibration"])
        selected_detectors = tuple(data["selected_detectors"])
        scored = data.get("scored", scored)
        typicality_refs = rehydrate_typicality_refs(data.get("typicality_refs"))
        if scored is not None and cache_key not in _LR_SCORED_CACHE:
            _LR_SCORED_CACHE[cache_key] = scored.copy()
        return model, calibration, feature_cols, selected_detectors, scored, typicality_refs
    except Exception:
        return None


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
    augmented_reference: bool = False,
    sample_multiplier: int = 1,
    scored: pd.DataFrame | None = None,
    use_latent_typicality: bool = False,
    typicality_refs: dict[str, TypicalityReference] | None = None,
    typicality_system: str = DEFAULT_TYPICALITY_SYSTEM,
    typicality_k: int = DEFAULT_TYPICALITY_K,
    typicality_distance: str = DEFAULT_TYPICALITY_DISTANCE,
) -> dict[str, Any]:
    if scored is None:
        scored = _score_dataframe(split, model, calibration, feature_cols)
    test = scored[scored["reference_split"].eq("test_bigauss")].copy()

    if use_latent_typicality:
        if typicality_refs is None:
            raise RuntimeError("typicality_refs ausente para pontuar evidencia com tipicidade.")
        features = _build_questioned_features(
            detector_scores,
            selected_detectors,
            typicality_refs,
            typicality_system=typicality_system,
        )
    else:
        features = _detector_features(detector_scores, selected_detectors)
    questioned = _apply(model, calibration, features)

    plot_dir = out_dir
    tippett_name = "lr_reference_tippett.png"
    distribution_name = "lr_reference_distribution.png"
    identity_name = "lr_reference_identity.png"
    summary_name = "lr_reference_summary.txt"
    _plot_tippett(plot_dir / tippett_name, test, "Tippett plot")
    _plot_distribution(
        plot_dir / distribution_name,
        test,
        "Distribuicao das LRs - populacao de referencia",
        questioned_log10_lr=questioned.get("log10_lr"),
    )
    identity_mse = _plot_identity(plot_dir / identity_name, test, "Funcao identidade - populacao de referencia")

    feature_weights = _classifier_feature_importance(model, feature_cols)
    sample_rows = int(len(scored)) if scored is not None else int(len(split))
    report: dict[str, Any] = {
        "hypothesis_positive": "real_authentic",
        "hypothesis_negative": "synthetic_ai_generated",
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
        "sample_rows": sample_rows,
        "fit_sample_rows": int(
            scored["reference_split"].astype(str).isin(FIT_REFERENCE_SPLITS).sum()
        ),
        "test_sample_rows": int(
            (scored["reference_split"].astype(str) == TEST_REFERENCE_SPLIT).sum()
        ),
        "augmented_reference": bool(augmented_reference),
        "sample_multiplier": int(sample_multiplier),
        "use_latent_typicality": bool(use_latent_typicality),
        "typicality_system": typicality_system if use_latent_typicality else None,
        "typicality_k": int(typicality_k) if use_latent_typicality else None,
        "typicality_distance": typicality_distance if use_latent_typicality else None,
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
        "feature_values": {
            col: float(val) for col, val in zip(feature_cols, np.asarray(features, dtype=float).ravel())
        },
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
        "note": "LR > 1 favorece H1=real/autentica; LR < 1 favorece H0=sintetica/gerada por IA.",
        "used_cache": used_cache,
    }
    if classifier == "logistic":
        report["logreg_coefficients"] = feature_weights
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
    seed: int = 20260630,
    score_matrix: Path = DEFAULT_SCORE_MATRIX,
    selected_detectors: tuple[str, ...] = ALL_DETECTORS,
    classifier: str = DEFAULT_META_CLASSIFIER,
    sample_multiplier: int = 1,
    use_latent_typicality: bool = False,
    typicality_system: str = DEFAULT_TYPICALITY_SYSTEM,
    typicality_k: int = DEFAULT_TYPICALITY_K,
    typicality_distance: str = DEFAULT_TYPICALITY_DISTANCE,
) -> dict[str, Any]:
    import logging
    import time

    log = logging.getLogger(__name__)
    selected_detectors = tuple(detector for detector in ALL_DETECTORS if detector in selected_detectors)
    if not selected_detectors:
        raise RuntimeError("Pelo menos um detector deve ser selecionado para calibracao LR.")
    classifier = _validate_classifier(classifier)
    sample_multiplier = max(1, int(sample_multiplier))

    use_latent_typicality = bool(use_latent_typicality)
    if use_latent_typicality and feature_columns_for_detectors is None:
        raise RuntimeError("latent_typicality module is not available")

    if use_latent_typicality:
        resolved = score_matrix.resolve()
        effective_score_matrix = (
            DEFAULT_REPRESENTATIONS_MATRIX
            if resolved in _SCORE_ONLY_MATRICES
            else score_matrix
        )
    else:
        effective_score_matrix = score_matrix

    feature_cols = (
        feature_columns_for_detectors(typicality_system, selected_detectors)
        if use_latent_typicality
        else _feature_cols(selected_detectors)
    )

    roles = normalize_reference_selection_roles(selection)
    if not roles.fit_items:
        raise RuntimeError("Pelo menos um subgrupo em fit_items e necessario para calibracao LR.")
    if not roles.test_items:
        raise RuntimeError("Pelo menos um subgrupo em test_items e necessario para metricas de teste.")
    items = list(roles.union_items)
    macro_category = _macro_category_for_selection(selection)
    augmented_reference = sample_multiplier > 1
    key_parts = dict(
        macro_category=macro_category,
        items=items,
        fit_items=list(roles.fit_items),
        test_items=list(roles.test_items),
        selected_detectors=selected_detectors,
        classifier=classifier,
        seed=seed,
        sample_multiplier=sample_multiplier,
        use_latent_typicality=use_latent_typicality,
        typicality_system=typicality_system,
        typicality_k=typicality_k,
        typicality_distance=typicality_distance,
    )

    # Cache-first: probe legacy joblib names BEFORE reading the multi-hundred-MB CSV.
    t0 = time.perf_counter()
    hash_candidates: list[str] = []
    if use_latent_typicality:
        hash_candidates.extend(_LEGACY_REPS_MATRIX_HASHES)

    cache_keys: list[str] = []
    seen_keys: set[str] = set()
    for matrix_hash in hash_candidates:
        key = _cache_key_from_parts(score_matrix_hash=matrix_hash, **key_parts)
        if key not in seen_keys:
            seen_keys.add(key)
            cache_keys.append(key)

    cached = None
    hit_key: str | None = None
    used_cache = False
    model: Any = None
    calibration: dict[str, Any] | None = None
    scored: pd.DataFrame | None = None
    typicality_refs: dict[str, TypicalityReference] | None = None

    def _try_keys(keys: list[str]) -> bool:
        nonlocal cached, hit_key, used_cache, model, calibration, scored, typicality_refs
        for candidate_key in keys:
            path = _cache_dir() / f"{candidate_key}.joblib"
            if not path.is_file():
                continue
            print(
                f"[synthetic_lr] trying cache {candidate_key} ({path.stat().st_size / 1e6:.0f} MB)…",
                flush=True,
            )
            candidate = _load_lr_cache(candidate_key)
            if candidate is None:
                continue
            (
                model,
                calibration,
                cached_feature_cols,
                cached_detectors,
                scored,
                typicality_refs,
            ) = candidate
            if cached_feature_cols == feature_cols and cached_detectors == selected_detectors:
                cached = candidate
                hit_key = candidate_key
                used_cache = True
                return True
            cached = None
            scored = None
            typicality_refs = None
            model = None
            calibration = None
        return False

    if not _try_keys(cache_keys):
        # Prefer path-stable hash (sidecar-cached); only then pay for raw SHA
        # and only if the primary key still misses.
        stable_hash = _score_matrix_hash(effective_score_matrix)
        stable_key = _cache_key_from_parts(score_matrix_hash=stable_hash, **key_parts)
        if stable_key not in seen_keys:
            seen_keys.add(stable_key)
            cache_keys.append(stable_key)
        if not _try_keys([stable_key]):
            raw_hash = _raw_file_hash(effective_score_matrix)
            raw_key = _cache_key_from_parts(score_matrix_hash=raw_hash, **key_parts)
            if raw_key not in seen_keys:
                seen_keys.add(raw_key)
                cache_keys.append(raw_key)
            _try_keys([raw_key])

    cache_key = cache_keys[-1] if cache_keys else _cache_key(
        score_matrix=effective_score_matrix, **key_parts
    )

    if used_cache:
        msg = (
            f"[synthetic_lr] CACHE HIT key={hit_key} primary={cache_key} "
            f"items={len(items)} latent={use_latent_typicality} mult={sample_multiplier} "
            f"in {time.perf_counter() - t0:.1f}s"
        )
        print(msg, flush=True)
        log.info(msg)
        if hit_key and hit_key != cache_key:
            _alias_lr_cache(cache_key, hit_key)
        # Rewrite bloated legacy caches (sklearn k-NN trees) into slim float32 form.
        try:
            hit_path = _cache_dir() / f"{hit_key}.joblib"
            if (
                hit_path.is_file()
                and hit_path.stat().st_size > 1_500_000_000
                and typicality_refs is not None
                and model is not None
                and calibration is not None
            ):
                print(
                    f"[synthetic_lr] rewriting slim cache {hit_key} "
                    f"({hit_path.stat().st_size / 1e6:.0f} MB → compress+float32)…",
                    flush=True,
                )
                _save_lr_cache(
                    cache_key=cache_key,
                    model=model,
                    calibration=calibration,
                    feature_cols=feature_cols,
                    selected_detectors=selected_detectors,
                    metadata={
                        "classifier": classifier,
                        "seed": seed,
                        "selected_count": len(items),
                        "fit_count": len(roles.fit_items),
                        "test_count": len(roles.test_items),
                        "score_matrix_hash": _score_matrix_hash(effective_score_matrix),
                        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
                        "use_latent_typicality": use_latent_typicality,
                        "sample_multiplier": sample_multiplier,
                        "slim_rewrite": True,
                    },
                    scored=scored,
                    typicality_refs=typicality_refs,
                )
                new_path = _cache_dir() / f"{cache_key}.joblib"
                print(
                    f"[synthetic_lr] slim cache now {new_path.stat().st_size / 1e6:.1f} MB",
                    flush=True,
                )
        except Exception as exc:
            print(f"[synthetic_lr] slim rewrite skipped: {exc}", flush=True)
        assert model is not None and calibration is not None and scored is not None
        return _build_report(
            model=model,
            calibration=calibration,
            feature_cols=feature_cols,
            selected_detectors=selected_detectors,
            roles=roles,
            split=scored,
            detector_scores=detector_scores,
            classifier=classifier,
            out_dir=out_dir,
            used_cache=True,
            augmented_reference=augmented_reference,
            sample_multiplier=sample_multiplier,
            scored=scored,
            use_latent_typicality=use_latent_typicality,
            typicality_refs=typicality_refs,
            typicality_system=typicality_system,
            typicality_k=typicality_k,
            typicality_distance=typicality_distance,
        )

    msg = (
        f"[synthetic_lr] CACHE MISS keys={cache_keys} items={len(items)} "
        f"latent={use_latent_typicality} mult={sample_multiplier} → full calibrate"
    )
    print(msg, flush=True)
    log.info(msg)

    df = _load_scores(effective_score_matrix)
    if use_latent_typicality:
        print(
            f"[synthetic_lr] filtering embeddings on {len(df)} rows…",
            flush=True,
        )
        df = _filter_rows_with_embeddings(df, selected_detectors)
        if df.empty:
            raise RuntimeError(
                "Nenhuma linha com embeddings completos no disco para calibracao com tipicidade."
            )
        for detector in selected_detectors:
            df[f"{detector}_logit_prob"] = _logit_prob(df[f"{detector}_fake_prob"])

    df, augmented_reference, sample_multiplier, auto_promoted = _resolve_scope_for_population(
        df,
        items,
        augmented_reference=augmented_reference,
        sample_multiplier=sample_multiplier,
    )
    if df.empty:
        raise RuntimeError(
            "Nenhuma linha disponivel apos filtro de escopo "
            + ("(referencia aumentada)" if augmented_reference else "(somente originais)")
        )
    if auto_promoted:
        key_parts["sample_multiplier"] = sample_multiplier
        msg = (
            "[synthetic_lr] auto-habilitou referencia aumentada "
            f"(mult={sample_multiplier}) — originais ausentes na matriz para: "
            + ", ".join(auto_promoted)
        )
        print(msg, flush=True)
        log.info(msg)
        # Re-probe cache under the promoted multiplier before full calibrate.
        promoted_hash = _score_matrix_hash(effective_score_matrix)
        promoted_key = _cache_key_from_parts(score_matrix_hash=promoted_hash, **key_parts)
        if promoted_key not in seen_keys:
            seen_keys.add(promoted_key)
            cache_keys.append(promoted_key)
        if _try_keys([promoted_key]):
            cache_key = hit_key or promoted_key
            assert model is not None and calibration is not None and scored is not None
            return _build_report(
                model=model,
                calibration=calibration,
                feature_cols=feature_cols,
                selected_detectors=selected_detectors,
                roles=roles,
                split=scored,
                detector_scores=detector_scores,
                classifier=classifier,
                out_dir=out_dir,
                used_cache=True,
                augmented_reference=augmented_reference,
                sample_multiplier=sample_multiplier,
                scored=scored,
                use_latent_typicality=use_latent_typicality,
                typicality_refs=typicality_refs,
                typicality_system=typicality_system,
                typicality_k=typicality_k,
                typicality_distance=typicality_distance,
            )
        cache_key = promoted_key

    role_label = (
        f" (fit {len(roles.fit_items)}, test {len(roles.test_items)})"
        if roles.fit_keys != roles.test_keys or roles.fit_items != roles.test_items
        else ""
    )
    print(
        f"[synthetic_lr] building sample/splits for {len(items)} subgroups{role_label} "
        f"(mult={sample_multiplier})…",
        flush=True,
    )
    sample = _build_reference_sample(df, items, seed, sample_multiplier=sample_multiplier)
    split = _assign_splits(sample, seed, sample_multiplier=sample_multiplier)
    split = _filter_working_split(split, roles)

    train = split[split["reference_split"].eq("train_logreg")]
    if use_latent_typicality:
        print(
            f"[synthetic_lr] building typicality refs on train={len(train)} rows…",
            flush=True,
        )
        typicality_refs = _build_typicality_refs(
            train,
            selected_detectors,
            typicality_k,
            typicality_distance,
        )
        train = _materialize_typicality_features(
            train.copy(), typicality_refs, selected_detectors
        )
        split = pd.concat(
            [split[split["reference_split"].ne("train_logreg")], train],
            ignore_index=True,
        )
        for split_name in ("calibration_bigauss", "test_bigauss"):
            split_part = split[split["reference_split"].eq(split_name)]
            if not split_part.empty:
                split_part = _materialize_typicality_features(
                    split_part.copy(), typicality_refs, selected_detectors
                )
                split = pd.concat(
                    [split[split["reference_split"].ne(split_name)], split_part],
                    ignore_index=True,
                )

    x_train = train[feature_cols].to_numpy(dtype=float)
    y_train = (1 - train["y_fake"].astype(int)).to_numpy()
    model = _train_meta_classifier(classifier, x_train, y_train, feature_cols, seed)
    calibration = _fit_bigauss(split, model, feature_cols)
    scored = _score_dataframe(split, model, calibration, feature_cols)
    _save_lr_cache(
        cache_key=cache_key,
        model=model,
        calibration=calibration,
        feature_cols=feature_cols,
        selected_detectors=selected_detectors,
        metadata={
            "macro_category": macro_category,
            "score_matrix_hash": _score_matrix_hash(effective_score_matrix),
            "classifier": classifier,
            "seed": seed,
            "sample_multiplier": sample_multiplier,
            "selected_count": len(items),
            "fit_count": len(roles.fit_items),
            "test_count": len(roles.test_items),
            "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "use_latent_typicality": use_latent_typicality,
            "typicality_system": typicality_system,
            "typicality_k": typicality_k,
            "typicality_distance": typicality_distance,
        },
        scored=scored,
        typicality_refs=typicality_refs,
    )
    print(
        f"[synthetic_lr] calibrated+cached in {time.perf_counter() - t0:.1f}s key={cache_key}",
        flush=True,
    )

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
        used_cache=False,
        augmented_reference=augmented_reference,
        sample_multiplier=sample_multiplier,
        scored=scored,
        use_latent_typicality=use_latent_typicality,
        typicality_refs=typicality_refs,
        typicality_system=typicality_system,
        typicality_k=typicality_k,
        typicality_distance=typicality_distance,
    )
