"""Reference-population LR calibration for synthetic-image detection.

Prototype service for a selectable reference population:
- uses stored detector scores as the reference population;
- trains a meta LogisticRegression on detector logit(fake_prob) features;
- calibrates the meta-score with EER-based bi-Gaussianized calibration;
- reports LR with positive values favoring H1 = real/authentic.
"""

from __future__ import annotations

import json
import math
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
from sklearn.ensemble import (
    ExtraTreesClassifier,
    GradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import GridSearchCV
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KernelDensity
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures
from sklearn.svm import SVC
from xgboost import XGBClassifier

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


ALL_DETECTORS = ("ai_image_detector_deploy", "sdxl_flux_detector_v1_1", "bfree", "corvi2023", "safe")
FEATURE_COLS_FOR_DETECTORS = {detector: f"{detector}_logit_prob" for detector in ALL_DETECTORS}
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCORE_MATRIX = PROJECT_ROOT / "outputs/lr_calibration/score_matrices/lr_scores_balanced_full.csv"
SAMPLE_PER_CLASS = 500
TRAIN_PER_CLASS = 250
CALIB_PER_CLASS = 125
TEST_PER_CLASS = 125

# In-memory caches to avoid repeated I/O and scoring on the same reference population.
# Key for score matrix: (resolved path string, mtime, size).
_SCORE_MATRIX_DF_CACHE: dict[tuple[str, float, int], pd.DataFrame] = {}
# Key for scored reference population: cache_key from compute_reference_lr.
_LR_SCORED_CACHE: dict[str, pd.DataFrame] = {}

META_CLASSIFIERS = (
    "logistic",
    "logistic_poly2",
    "xgboost",
    "gradient_boosting",
    "random_forest",
    "extra_trees",
    "svm_rbf",
    "mlp",
    "kde_naive_bayes",
)
DEFAULT_META_CLASSIFIER = "logistic"

_CLASSIFIER_LABELS: dict[str, str] = {
    "logistic": "Regressao Logistica",
    "logistic_poly2": "Regressao Logistica (grau 2)",
    "xgboost": "XGBoost",
    "gradient_boosting": "Gradient Boosting",
    "random_forest": "Random Forest",
    "extra_trees": "Extra Trees",
    "svm_rbf": "SVM (RBF)",
    "mlp": "MLP (rede neural)",
    "kde_naive_bayes": "KDE Naive Bayes",
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
    if not selection:
        return _default_items()

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
    return ordered or _default_items()


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
    raise ValueError(f"Unknown reference item: {item}")


def _sample_rows(df: pd.DataFrame, n: int, rng: np.random.Generator, context: str) -> pd.DataFrame:
    if len(df) >= n:
        return df.sample(n=n, random_state=int(rng.integers(0, 2**31 - 1))).copy()
    # Small population: sample with replacement so the pipeline can still be trained.
    return df.sample(n=n, replace=True, random_state=int(rng.integers(0, 2**31 - 1))).copy()


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
    if classifier not in META_CLASSIFIERS:
        raise RuntimeError(
            f"Classificador meta '{classifier}' nao suportado. "
            f"Use um de: {', '.join(META_CLASSIFIERS)}"
        )
    if classifier == "random_forest" and RandomForestClassifier is None:
        raise RuntimeError("RandomForestClassifier nao esta disponivel neste ambiente.")
    return classifier


def _bandwidth_grid_search(x: np.ndarray, y: np.ndarray) -> float:
    """Select KDE bandwidth via 3-fold cross-validated log-likelihood."""
    if len(np.unique(y)) < 2 or len(x) < 30:
        return "scott"
    params = {"bandwidth": np.logspace(-1.5, 0.5, 7)}
    grid = GridSearchCV(
        KernelDensity(kernel="gaussian"),
        params,
        cv=3,
        scoring=lambda estimator, x, y: estimator.score_samples(x).sum(),
    )
    grid.fit(x)
    return float(grid.best_params_["bandwidth"])


class _KdeNaiveBayesClassifier:
    """Naive-Bayes-like KDE ensemble: one KDE per class on full detector-logit vectors."""

    def __init__(self, bandwidth: float | str = "scott"):
        self.bandwidth = bandwidth
        self.kde_real_: KernelDensity | None = None
        self.kde_fake_: KernelDensity | None = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> "_KdeNaiveBayesClassifier":
        x_real = x[y == 1]
        x_fake = x[y == 0]
        if len(x_real) < 2 or len(x_fake) < 2:
            raise RuntimeError("KDE requer pelo menos 2 amostras por classe.")
        bandwidth = self.bandwidth
        if bandwidth == "auto":
            bandwidth = _bandwidth_grid_search(x, y)
        self.kde_real_ = KernelDensity(kernel="gaussian", bandwidth=bandwidth)
        self.kde_fake_ = KernelDensity(kernel="gaussian", bandwidth=bandwidth)
        self.kde_real_.fit(x_real)
        self.kde_fake_.fit(x_fake)
        return self

    def decision_function(self, x: np.ndarray) -> np.ndarray:
        if self.kde_real_ is None or self.kde_fake_ is None:
            raise RuntimeError("KDE nao foi treinado.")
        log_real = self.kde_real_.score_samples(x)
        log_fake = self.kde_fake_.score_samples(x)
        return (log_real - log_fake).astype(float)


class _GaussianNbClassifier:
    """Gaussian Naive Bayes exposing a decision_function as log-likelihood ratio."""

    def __init__(self) -> None:
        self.model_ = GaussianNB()

    def fit(self, x: np.ndarray, y: np.ndarray) -> "_GaussianNbClassifier":
        self.model_.fit(x, y)
        return self

    def decision_function(self, x: np.ndarray) -> np.ndarray:
        log_prob = self.model_.predict_joint_log_proba(x)
        return (log_prob[:, 1] - log_prob[:, 0]).astype(float)


def _train_meta_classifier(
    classifier: str,
    x: np.ndarray,
    y: np.ndarray,
    feature_cols: list[str],
    seed: int,
) -> Any:
    """Train a meta-classifier on detector logit features."""
    classifier = _validate_classifier(classifier)
    if classifier == "logistic":
        model = LogisticRegression(C=1.0, max_iter=2000, solver="lbfgs", random_state=seed)
    elif classifier == "logistic_poly2":
        model = Pipeline(
            [
                ("poly", PolynomialFeatures(degree=2, include_bias=False)),
                ("logreg", LogisticRegression(C=1.0, max_iter=2000, solver="lbfgs", random_state=seed)),
            ]
        )
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
    elif classifier == "gradient_boosting":
        model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.1,
            subsample=0.9,
            random_state=seed,
        )
    elif classifier == "random_forest":
        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=None,
            min_samples_leaf=5,
            random_state=seed,
            n_jobs=4,
        )
    elif classifier == "extra_trees":
        model = ExtraTreesClassifier(
            n_estimators=200,
            max_depth=None,
            min_samples_leaf=5,
            random_state=seed,
            n_jobs=4,
        )
    elif classifier == "svm_rbf":
        model = SVC(kernel="rbf", C=1.0, gamma="scale", probability=False, random_state=seed)
    elif classifier == "mlp":
        model = MLPClassifier(
            hidden_layer_sizes=(16, 8),
            activation="relu",
            solver="adam",
            alpha=1e-3,
            max_iter=2000,
            random_state=seed,
            early_stopping=True,
            validation_fraction=0.15,
        )
    elif classifier == "kde_naive_bayes":
        model = _KdeNaiveBayesClassifier(bandwidth="scott")
    elif classifier == "gaussian_nb":
        model = _GaussianNbClassifier()
    else:
        raise RuntimeError(f"Classificador nao implementado: {classifier}")
    model.fit(x, y)
    return model


def _classifier_decision_scores(model: Any, x: np.ndarray) -> np.ndarray:
    """Return a real-valued score in the direction real > synthetic.

    For probabilistic classifiers (LogisticRegression, XGBoost, RandomForest),
    use logit(p_real). For SVM, use decision_function.
    """
    if hasattr(model, "decision_function"):
        return np.asarray(model.decision_function(x), dtype=float)
    proba = np.asarray(model.predict_proba(x), dtype=float)
    p_real = np.clip(proba[:, 1], 1e-6, 1.0 - 1e-6)
    return _logit_prob(p_real)


def _classifier_feature_importance(model: Any, feature_cols: list[str]) -> dict[str, float] | None:
    """Return feature importance/coefficients when available and interpretable."""
    if isinstance(model, Pipeline):
        # Polynomial expansion changes feature semantics; skip interpretable weights.
        return None
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
    path = PROJECT_ROOT / "outputs" / "lr_calibration" / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _score_matrix_hash(score_matrix: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(score_matrix, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _macro_category_for_selection(selection: Any) -> str | None:
    """Return macro category id if selection matches exactly one macro category."""
    items = normalize_reference_selection(selection)
    item_set = {item.key for item in items}
    for macro_id, macro in REFERENCE_MACRO_CATEGORIES.items():
        macro_set = {item.key for item in macro["items"]}
        if item_set == macro_set:
            return macro_id
    return None


def _cache_key(
    *,
    score_matrix: Path,
    macro_category: str | None,
    items: list[PopulationItem],
    selected_detectors: tuple[str, ...],
    classifier: str,
    seed: int,
    sample_multiplier: int = 1,
) -> str:
    import hashlib

    canonical = {
        "score_matrix_hash": _score_matrix_hash(score_matrix),
        "macro_category": macro_category,
        "items": sorted(item.key for item in items) if macro_category is None else [],
        "selected_detectors": list(selected_detectors),
        "classifier": classifier,
        "seed": seed,
        "sample_multiplier": sample_multiplier,
        "sample_per_class": SAMPLE_PER_CLASS,
    }
    payload = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


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
) -> Path:
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
    joblib.dump(payload, path)
    if scored is not None:
        _LR_SCORED_CACHE[cache_key] = scored.copy()
    return path


def _load_lr_cache(
    cache_key: str,
) -> tuple[Any, dict[str, Any], list[str], tuple[str, ...], pd.DataFrame | None] | None:
    if cache_key in _LR_SCORED_CACHE:
        scored = _LR_SCORED_CACHE[cache_key]
    else:
        scored = None

    path = _cache_dir() / f"{cache_key}.joblib"
    if not path.is_file():
        if scored is not None:
            return None, None, [], (), scored
        return None
    try:
        data = joblib.load(path)
        model = data["model"]
        feature_cols = list(data["feature_cols"])
        calibration = _deserialize_calibration(data["calibration"])
        selected_detectors = tuple(data["selected_detectors"])
        scored = data.get("scored", scored)
        if scored is not None and cache_key not in _LR_SCORED_CACHE:
            _LR_SCORED_CACHE[cache_key] = scored.copy()
        return model, calibration, feature_cols, selected_detectors, scored
    except Exception:
        return None


def _build_report(
    *,
    model: Any,
    calibration: dict[str, Any],
    feature_cols: list[str],
    selected_detectors: tuple[str, ...],
    items: list[PopulationItem],
    split: pd.DataFrame,
    detector_scores: dict[str, Any],
    classifier: str,
    out_dir: Path,
    used_cache: bool,
    augmented_reference: bool = False,
    sample_multiplier: int = 1,
    scored: pd.DataFrame | None = None,
) -> dict[str, Any]:
    if scored is None:
        scored = _score_dataframe(split, model, calibration, feature_cols)
    test = scored[scored["reference_split"].eq("test_bigauss")].copy()

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
    report: dict[str, Any] = {
        "hypothesis_positive": "real_authentic",
        "hypothesis_negative": "synthetic_ai_generated",
        "sample_per_class_per_subgroup": SAMPLE_PER_CLASS,
        "selected_items": [{"base_group": item.base_group, "subgroup": item.subgroup, "key": item.key} for item in items],
        "selected_count": len(items),
        "sample_rows": int(len(split)),
        "augmented_reference": bool(augmented_reference),
        "sample_multiplier": int(sample_multiplier),
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
) -> dict[str, Any]:
    selected_detectors = tuple(detector for detector in ALL_DETECTORS if detector in selected_detectors)
    if not selected_detectors:
        raise RuntimeError("Pelo menos um detector deve ser selecionado para calibracao LR.")
    classifier = _validate_classifier(classifier)
    sample_multiplier = max(1, int(sample_multiplier))

    feature_cols = _feature_cols(selected_detectors)
    items = normalize_reference_selection(selection)
    df = _load_scores(score_matrix)
    sample = _build_reference_sample(df, items, seed, sample_multiplier=sample_multiplier)
    split = _assign_splits(sample, seed, sample_multiplier=sample_multiplier)

    augmented_reference = sample_multiplier > 1

    macro_category = _macro_category_for_selection(selection)
    cache_key = _cache_key(
        score_matrix=score_matrix,
        macro_category=macro_category,
        items=items,
        selected_detectors=selected_detectors,
        classifier=classifier,
        seed=seed,
        sample_multiplier=sample_multiplier,
    )
    cached = _load_lr_cache(cache_key)
    used_cache = False
    scored: pd.DataFrame | None = None

    if cached is not None:
        model, calibration, cached_feature_cols, cached_detectors, scored = cached
        if cached_feature_cols == feature_cols and cached_detectors == selected_detectors:
            used_cache = True
        else:
            cached = None
            scored = None

    if cached is None:
        train = split[split["reference_split"].eq("train_logreg")]
        x_train = train[feature_cols].to_numpy(dtype=float)
        y_train = (1 - train["y_fake"].astype(int)).to_numpy()
        model = _train_meta_classifier(classifier, x_train, y_train, feature_cols, seed)
        calibration = _fit_bigauss(split, model, feature_cols)

    if scored is None:
        scored = _score_dataframe(split, model, calibration, feature_cols)
        _save_lr_cache(
            cache_key=cache_key,
            model=model,
            calibration=calibration,
            feature_cols=feature_cols,
            selected_detectors=selected_detectors,
            metadata={
                "macro_category": macro_category,
                "score_matrix_hash": _score_matrix_hash(score_matrix),
                "classifier": classifier,
                "seed": seed,
                "selected_count": len(items),
                "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
            },
            scored=scored,
        )

    return _build_report(
        model=model,
        calibration=calibration,
        feature_cols=feature_cols,
        selected_detectors=selected_detectors,
        items=items,
        split=split,
        detector_scores=detector_scores,
        classifier=classifier,
        out_dir=out_dir,
        used_cache=used_cache,
        augmented_reference=augmented_reference,
        sample_multiplier=sample_multiplier,
        scored=scored,
    )
