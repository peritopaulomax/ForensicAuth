#!/usr/bin/env python3
"""Run LogReg ensemble plus bi-Gaussianized LR calibration.

This experiment reuses an existing detector score matrix. It builds a uniform
150-real/150-fake sample per dataset generator/subset, trains a multivariate
LogReg meta-score on 50%, calibrates that score with Morrison's EER-based
bi-Gaussianized mapping on 25%, and evaluates on the remaining 25%.
"""

from __future__ import annotations

import argparse
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
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score, roc_curve

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


DETECTORS = ("ai_image_detector_deploy", "sdxl_flux_detector_v1_1", "bfree", "corvi2023")
FEATURE_COLS = [f"{detector}_logit_prob" for detector in DETECTORS]
SAMPLE_PER_CLASS = 150
TRAIN_PER_CLASS = 75
CALIB_PER_CLASS = 38
TEST_PER_CLASS = 37


@dataclass(frozen=True)
class SubgroupSpec:
    base_group: str
    subgroup: str
    fake_query: pd.Series
    real_query: pd.Series | None = None
    real_pool: str | None = None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _logit_prob(series: pd.Series, eps: float = 1e-6) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").clip(eps, 1.0 - eps)
    return np.log(values / (1.0 - values))


def _add_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for detector in DETECTORS:
        out[f"{detector}_logit_prob"] = _logit_prob(out[f"{detector}_fake_prob"])
    return out


def _sample_rows(df: pd.DataFrame, n: int, rng: np.random.Generator, context: str) -> pd.DataFrame:
    if len(df) < n:
        raise RuntimeError(f"Not enough rows for {context}: requested={n}, available={len(df)}")
    return df.sample(n=n, random_state=int(rng.integers(0, 2**31 - 1))).copy()


def _prepare_score_matrix(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df = df[df["error"].fillna("").eq("")].copy()
    df["y_fake"] = df["y_fake"].astype(int)
    return _add_features(df)


def _build_specs(df: pd.DataFrame) -> list[SubgroupSpec]:
    specs: list[SubgroupSpec] = []

    genimage = df[df["dataset"].eq("GenImage")]
    for generator in sorted(genimage["generator"].unique()):
        specs.append(
            SubgroupSpec(
                base_group="GenImage",
                subgroup=str(generator),
                fake_query=df["dataset"].eq("GenImage") & df["generator"].eq(generator) & df["y_fake"].eq(1),
                real_query=df["dataset"].eq("GenImage") & df["generator"].eq(generator) & df["y_fake"].eq(0),
            )
        )

    defactify = df[df["dataset"].eq("Defactify_MS_COCOAI")]
    for generator in sorted(defactify.loc[defactify["y_fake"].eq(1), "generator"].unique()):
        specs.append(
            SubgroupSpec(
                base_group="Defactify",
                subgroup=str(generator),
                fake_query=df["dataset"].eq("Defactify_MS_COCOAI") & df["generator"].eq(generator) & df["y_fake"].eq(1),
                real_pool="Defactify",
            )
        )

    aigc = df[df["dataset"].eq("AIGCDetectBenchmark")]
    for generator in sorted(aigc.loc[aigc["y_fake"].eq(1), "generator"].unique()):
        specs.append(
            SubgroupSpec(
                base_group="AIGCDetectBenchmark",
                subgroup=str(generator),
                fake_query=df["dataset"].eq("AIGCDetectBenchmark") & df["generator"].eq(generator) & df["y_fake"].eq(1),
                real_pool="AIGCDetectBenchmark",
            )
        )

    opensdi = df[df["dataset"].eq("OpenSDI_test")]
    for generator in sorted(opensdi.loc[opensdi["y_fake"].eq(1), "generator"].unique()):
        specs.append(
            SubgroupSpec(
                base_group="OpenSDI",
                subgroup=str(generator),
                fake_query=df["dataset"].eq("OpenSDI_test") & df["generator"].eq(generator) & df["y_fake"].eq(1),
                real_pool="OpenSDI",
            )
        )

    aigibench = df[df["dataset"].eq("AIGIBench")]
    for generator in ("CommunityAI", "DALLE-3", "FLUX1-dev", "SD3"):
        specs.append(
            SubgroupSpec(
                base_group="AIGIBench_no_SocialRF",
                subgroup=generator,
                fake_query=df["dataset"].eq("AIGIBench") & df["generator"].eq(generator) & df["y_fake"].eq(1),
                real_query=df["dataset"].eq("AIGIBench") & df["generator"].eq(f"{generator}_real") & df["y_fake"].eq(0),
            )
        )

    specs.append(
        SubgroupSpec(
            base_group="AIGIBench_SocialRF",
            subgroup="SocialRF",
            fake_query=df["dataset"].eq("AIGIBench") & df["generator"].eq("SocialRF") & df["y_fake"].eq(1),
            real_query=df["dataset"].eq("AIGIBench") & df["generator"].eq("SocialRF_real") & df["y_fake"].eq(0),
        )
    )
    return specs


def _real_pools(df: pd.DataFrame, rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    pools = {
        "Defactify": df[df["dataset"].eq("Defactify_MS_COCOAI") & df["y_fake"].eq(0)],
        "AIGCDetectBenchmark": df[df["dataset"].eq("AIGCDetectBenchmark") & df["y_fake"].eq(0)],
        "OpenSDI": df[df["dataset"].eq("OpenSDI_test") & df["y_fake"].eq(0)],
    }
    return {
        name: pool.sample(frac=1.0, random_state=int(rng.integers(0, 2**31 - 1))).reset_index(drop=False)
        for name, pool in pools.items()
    }


def build_uniform_sample(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    specs = _build_specs(df)
    pools = _real_pools(df, rng)
    pool_offsets = {name: 0 for name in pools}

    selected_frames: list[pd.DataFrame] = []
    for spec in specs:
        fake = _sample_rows(df[spec.fake_query], SAMPLE_PER_CLASS, rng, f"{spec.base_group}/{spec.subgroup}/fake")
        if spec.real_query is not None:
            real = _sample_rows(df[spec.real_query], SAMPLE_PER_CLASS, rng, f"{spec.base_group}/{spec.subgroup}/real")
        elif spec.real_pool is not None:
            pool = pools[spec.real_pool]
            start = pool_offsets[spec.real_pool]
            end = start + SAMPLE_PER_CLASS
            if end > len(pool):
                raise RuntimeError(f"Real pool exhausted for {spec.real_pool}: need up to {end}, available={len(pool)}")
            real = pool.iloc[start:end].drop(columns=["index"]).copy()
            pool_offsets[spec.real_pool] = end
        else:
            raise RuntimeError(f"Subgroup {spec.base_group}/{spec.subgroup} has no real source")

        for frame in (real, fake):
            frame["base_group"] = spec.base_group
            frame["subgroup"] = spec.subgroup
            frame["subgroup_key"] = f"{spec.base_group}/{spec.subgroup}"
        selected_frames.extend([real, fake])

    sample = pd.concat(selected_frames, ignore_index=True)
    expected = len(specs) * SAMPLE_PER_CLASS * 2
    if len(sample) != expected:
        raise RuntimeError(f"Unexpected sample size: got={len(sample)}, expected={expected}")
    return sample


def assign_splits(sample: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 1)
    parts: list[pd.DataFrame] = []
    for (subgroup_key, y_fake), group in sample.groupby(["subgroup_key", "y_fake"], sort=True):
        if len(group) != SAMPLE_PER_CLASS:
            raise RuntimeError(f"Expected {SAMPLE_PER_CLASS} rows for {subgroup_key}/y={y_fake}, got {len(group)}")
        shuffled = group.sample(frac=1.0, random_state=int(rng.integers(0, 2**31 - 1))).copy()
        shuffled["bigauss_split"] = (
            ["train_logreg"] * TRAIN_PER_CLASS
            + ["calibration_bigauss"] * CALIB_PER_CLASS
            + ["test_bigauss"] * TEST_PER_CLASS
        )
        parts.append(shuffled)
    return pd.concat(parts, ignore_index=True)


def _eer(y: np.ndarray, scores: np.ndarray) -> float:
    fpr, tpr, _thresholds = roc_curve(y, scores)
    fnr = 1.0 - tpr
    idx = int(np.nanargmin(np.abs(fnr - fpr)))
    return float((fpr[idx] + fnr[idx]) / 2.0)


def _cllr_ln(ln_lr: np.ndarray, y: np.ndarray) -> float:
    target = ln_lr[y == 1]
    nontarget = ln_lr[y == 0]
    if len(target) == 0 or len(nontarget) == 0:
        return float("nan")
    c1 = np.logaddexp(0.0, -target) / math.log(2.0)
    c0 = np.logaddexp(0.0, nontarget) / math.log(2.0)
    return float(0.5 * (np.mean(c1) + np.mean(c0)))


def _min_cllr_ln(ln_lr: np.ndarray, y: np.ndarray) -> float:
    if len(set(y.tolist())) < 2:
        return float("nan")
    order = np.argsort(ln_lr)
    iso = IsotonicRegression(out_of_bounds="clip")
    calibrated = iso.fit_transform(ln_lr[order], y[order])
    restored = np.empty_like(calibrated, dtype=float)
    restored[order] = calibrated
    p = np.clip(restored, 1e-6, 1 - 1e-6)
    return _cllr_ln(np.log(p / (1 - p)), y)


def _metrics(df: pd.DataFrame) -> dict[str, float | int]:
    y = df["y_fake"].astype(int).to_numpy()
    ln_lr = df["ln_lr"].to_numpy(dtype=float)
    prob = 1.0 / (1.0 + np.exp(-np.clip(ln_lr, -700, 700)))
    return {
        "rows": int(len(df)),
        "real_rows": int(np.sum(y == 0)),
        "fake_rows": int(np.sum(y == 1)),
        "cllr": _cllr_ln(ln_lr, y),
        "min_cllr": _min_cllr_ln(ln_lr, y),
        "auc": float(roc_auc_score(y, ln_lr)) if len(set(y.tolist())) == 2 else float("nan"),
        "eer": _eer(y, ln_lr) if len(set(y.tolist())) == 2 else float("nan"),
        "brier": float(brier_score_loss(y, prob)) if len(set(y.tolist())) == 2 else float("nan"),
        "log_loss": float(log_loss(y, prob, labels=[0, 1])) if len(set(y.tolist())) == 2 else float("nan"),
        "wrong_extreme_lr_count": int(np.sum(((y == 1) & (ln_lr < -2 * math.log(10))) | ((y == 0) & (ln_lr > 2 * math.log(10))))),
    }


def train_logreg(df: pd.DataFrame, c: float, max_iter: int) -> LogisticRegression:
    train = df[df["bigauss_split"].eq("train_logreg")]
    model = LogisticRegression(C=c, max_iter=max_iter, solver="lbfgs", random_state=20260630)
    model.fit(train[FEATURE_COLS].to_numpy(dtype=float), train["y_fake"].astype(int).to_numpy())
    return model


def fit_bigauss(df: pd.DataFrame, model: LogisticRegression) -> dict[str, Any]:
    calib = df[df["bigauss_split"].eq("calibration_bigauss")].copy()
    x = calib[FEATURE_COLS].to_numpy(dtype=float)
    y = calib["y_fake"].astype(int).to_numpy()
    z = model.decision_function(x).astype(float)

    eer = _eer(y, z)
    eer_for_sigma = float(np.clip(eer, 1e-6, 0.499999))
    sigma = float(-2.0 * norm.ppf(eer_for_sigma))
    if not np.isfinite(sigma) or sigma <= 0:
        raise RuntimeError(f"Invalid sigma from EER={eer}: {sigma}")

    order = np.argsort(z)
    z_sorted = z[order]
    y_sorted = y[order]
    n0 = int(np.sum(y == 0))
    n1 = int(np.sum(y == 1))
    weights = np.where(y_sorted == 1, 1.0 / (2.0 * (n1 + 1)), 1.0 / (2.0 * (n0 + 1)))
    cdf = np.cumsum(weights)

    unique_z, last_indices = np.unique(z_sorted, return_index=False, return_counts=False), []
    for value in unique_z:
        last_indices.append(int(np.where(z_sorted == value)[0][-1]))
    cdf_unique = cdf[np.array(last_indices, dtype=int)]

    empirical_cdf = interp1d(
        unique_z,
        cdf_unique,
        kind="linear",
        bounds_error=False,
        fill_value=(float(cdf_unique[0]), float(cdf_unique[-1])),
        assume_sorted=True,
    )

    mu0 = -sigma**2 / 2.0
    mu1 = sigma**2 / 2.0

    def mix_cdf(value: float) -> float:
        return float(0.5 * norm.cdf(value, mu0, sigma) + 0.5 * norm.cdf(value, mu1, sigma))

    y_min = mu0 - 12.0 * sigma
    y_max = mu1 + 12.0 * sigma

    def inv_cdf(p_value: float) -> float:
        p_float = float(np.clip(p_value, float(cdf_unique[0]), float(cdf_unique[-1])))
        return float(brentq(lambda value: mix_cdf(value) - p_float, y_min, y_max, maxiter=100))

    return {
        "eer": float(eer),
        "eer_for_sigma": eer_for_sigma,
        "sigma": sigma,
        "mu0": float(mu0),
        "mu1": float(mu1),
        "z_values": unique_z.astype(float),
        "cdf_values": cdf_unique.astype(float),
        "empirical_cdf": empirical_cdf,
        "inv_cdf": np.vectorize(inv_cdf),
    }


def apply_bigauss(df: pd.DataFrame, model: LogisticRegression, calibration: dict[str, Any]) -> pd.DataFrame:
    scored = df.copy()
    x = scored[FEATURE_COLS].to_numpy(dtype=float)
    z = model.decision_function(x).astype(float)
    p = calibration["empirical_cdf"](z).astype(float)
    ln_lr = calibration["inv_cdf"](p).astype(float)
    scored["logreg_z"] = z
    scored["bigauss_cdf_p"] = p
    scored["ln_lr"] = ln_lr
    scored["log10_lr"] = ln_lr / math.log(10.0)
    scored["lr"] = np.exp(np.clip(ln_lr, -700, 700))
    return scored


def _plot_tippett(path: Path, df: pd.DataFrame, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(8, 5))
    for y_value, label, color in ((0, "H0 real: proportion <= x", "red"), (1, "H1 synthetic: proportion >= x", "blue")):
        values = np.sort(df.loc[df["y_fake"].eq(y_value), "log10_lr"].to_numpy(dtype=float))
        if len(values) == 0:
            continue
        cumulative = np.arange(1, len(values) + 1) / len(values)
        y_axis = cumulative if y_value == 0 else 1.0 - np.arange(0, len(values)) / len(values)
        plt.step(values, y_axis, where="post", label=label, color=color)
    plt.axvline(0, color="black", linewidth=1, linestyle="--")
    plt.xlabel("log10 LR")
    plt.ylabel("Cumulative proportion")
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def _safe_kde(values: np.ndarray) -> gaussian_kde:
    if len(np.unique(values)) < 2:
        values = values + np.linspace(-1e-6, 1e-6, len(values))
    return gaussian_kde(values)


def _identity_stats_and_plot(path: Path, df: pd.DataFrame, title: str) -> dict[str, float]:
    path.parent.mkdir(parents=True, exist_ok=True)
    h0 = df.loc[df["y_fake"].eq(0), "ln_lr"].to_numpy(dtype=float)
    h1 = df.loc[df["y_fake"].eq(1), "ln_lr"].to_numpy(dtype=float)
    if len(h0) < 2 or len(h1) < 2:
        return {"identity_mse": float("nan")}
    kde0 = _safe_kde(h0)
    kde1 = _safe_kde(h1)
    lower = float(np.percentile(np.concatenate([h0, h1]), 1))
    upper = float(np.percentile(np.concatenate([h0, h1]), 99))
    grid = np.linspace(lower, upper, 500)
    density0 = np.maximum(kde0(grid), 1e-300)
    density1 = np.maximum(kde1(grid), 1e-300)
    log_ratio = np.log(density1 / density0)
    mse = float(np.mean((log_ratio - grid) ** 2))

    plt.figure(figsize=(6, 6))
    plt.plot(grid, log_ratio, label="KDE ln[p(lnLR|H1)/p(lnLR|H0)]")
    plt.plot(grid, grid, linestyle="--", label="identity")
    plt.xlabel("ln LR")
    plt.ylabel("density log-ratio")
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()
    return {"identity_mse": mse}


def _plot_distributions(path: Path, df: pd.DataFrame, calibration: dict[str, Any], title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    h0 = df.loc[df["y_fake"].eq(0), "ln_lr"].to_numpy(dtype=float)
    h1 = df.loc[df["y_fake"].eq(1), "ln_lr"].to_numpy(dtype=float)
    lower = float(np.percentile(np.concatenate([h0, h1]), 1))
    upper = float(np.percentile(np.concatenate([h0, h1]), 99))
    grid = np.linspace(lower, upper, 500)
    plt.figure(figsize=(8, 5))
    plt.plot(grid, _safe_kde(h0)(grid), color="red", linestyle="--", label="H0 empirical")
    plt.plot(grid, norm.pdf(grid, calibration["mu0"], calibration["sigma"]), color="red", alpha=0.5, label="H0 target")
    plt.plot(grid, _safe_kde(h1)(grid), color="blue", linestyle="--", label="H1 empirical")
    plt.plot(grid, norm.pdf(grid, calibration["mu1"], calibration["sigma"]), color="blue", alpha=0.5, label="H1 target")
    plt.axvline(0, color="black", linewidth=1, linestyle="--")
    plt.xlabel("ln LR")
    plt.ylabel("Density")
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def make_reports(scored: pd.DataFrame, model: LogisticRegression, calibration: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    test = scored[scored["bigauss_split"].eq("test_bigauss")].copy()
    report: dict[str, Any] = {
        "sample_rows": int(len(scored)),
        "test_rows": int(len(test)),
        "feature_cols": FEATURE_COLS,
        "logreg_coefficients": dict(zip(FEATURE_COLS, model.coef_[0].tolist())),
        "logreg_intercept": float(model.intercept_[0]),
        "bigauss": {
            "variant": "EER",
            "eer": calibration["eer"],
            "eer_for_sigma": calibration["eer_for_sigma"],
            "sigma": calibration["sigma"],
            "mu0": calibration["mu0"],
            "mu1": calibration["mu1"],
        },
        "split_counts": scored.groupby(["bigauss_split", "y_fake"]).size().to_dict(),
        "subgroup_counts": scored.groupby(["base_group", "subgroup", "y_fake"]).size().to_dict(),
        "overall": _metrics(test),
        "by_base_group": {},
        "by_subgroup": {},
        "plots": {},
    }

    plot_dir = out_dir / "plots"
    _plot_tippett(plot_dir / "tippett_overall.png", test, "Bi-Gaussianized LR Tippett - overall")
    report["plots"]["tippett_overall"] = str(plot_dir / "tippett_overall.png")
    identity = _identity_stats_and_plot(plot_dir / "identity_overall.png", test, "Bi-Gaussianized LR identity - overall")
    report["overall"].update(identity)
    report["plots"]["identity_overall"] = str(plot_dir / "identity_overall.png")
    _plot_distributions(plot_dir / "distributions_overall.png", test, calibration, "Bi-Gaussianized LR distributions - overall")
    report["plots"]["distributions_overall"] = str(plot_dir / "distributions_overall.png")

    for base_group, group in test.groupby("base_group", sort=True):
        metrics = _metrics(group)
        report["by_base_group"][base_group] = metrics
        safe = base_group.replace("/", "_")
        path = plot_dir / f"tippett_by_dataset_{safe}.png"
        _plot_tippett(path, group, f"Bi-Gaussianized LR Tippett - {base_group}")
        report["plots"][f"tippett_{base_group}"] = str(path)

    for (base_group, subgroup), group in test.groupby(["base_group", "subgroup"], sort=True):
        report["by_subgroup"][f"{base_group}/{subgroup}"] = _metrics(group)

    return report


def _stringify_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _stringify_keys(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stringify_keys(item) for item in value]
    return value


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# LogReg + Bi-Gaussianized Calibration",
        "",
        "## Modelo",
        f"- Amostra total: `{report['sample_rows']}`",
        f"- Teste: `{report['test_rows']}`",
        f"- Variante bi-Gauss: `{report['bigauss']['variant']}`",
        f"- EER calibração: `{report['bigauss']['eer']:.6f}`",
        f"- Sigma alvo: `{report['bigauss']['sigma']:.6f}`",
        "",
        "## Métricas Gerais No Teste",
        "| Linhas | Reais | Fakes | CLLR | minCLLR | AUC | EER | Identity MSE | LRs extremas erradas |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    m = report["overall"]
    lines.append(
        f"| {m['rows']} | {m['real_rows']} | {m['fake_rows']} | {m['cllr']:.4f} | {m['min_cllr']:.4f} | "
        f"{m['auc']:.4f} | {m['eer']:.4f} | {m.get('identity_mse', float('nan')):.4f} | {m['wrong_extreme_lr_count']} |"
    )
    lines.extend(
        [
            "",
            "## Métricas Por Base",
            "| Base | Linhas | Reais | Fakes | CLLR | minCLLR | AUC | EER | LRs extremas erradas |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for base_group, metrics in sorted(report["by_base_group"].items()):
        lines.append(
            f"| {base_group} | {metrics['rows']} | {metrics['real_rows']} | {metrics['fake_rows']} | "
            f"{metrics['cllr']:.4f} | {metrics['min_cllr']:.4f} | {metrics['auc']:.4f} | {metrics['eer']:.4f} | "
            f"{metrics['wrong_extreme_lr_count']} |"
        )
    lines.extend(
        [
            "",
            "## Riscos E Controles",
            "- O que pode falhar: 150+150 por subgrupo pode gerar variabilidade de calibração, sobretudo em domínios difíceis como SocialRF.",
            "- Como detectar: CLLR/minCLLR por base e subgrupo, identity plot, Tippett e contagem de LRs extremas erradas.",
            "- Como recuperar: repetir por múltiplas seeds, aumentar amostra para 500+500, comparar variantes LogReg/KDE para sigma ou aplicar shrinkage/truncagem.",
            "- Risco residual: pooling cross-domain pode produzir boa métrica global enquanto um domínio específico permanece mal calibrado.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--score-matrix", default="outputs/lr_calibration/score_matrices/lr_scores_balanced_full.csv")
    parser.add_argument("--out-dir", default="outputs/lr_bigauss_150")
    parser.add_argument("--seed", type=int, default=20260630)
    parser.add_argument("--c", type=float, default=1.0)
    parser.add_argument("--max-iter", type=int, default=2000)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    if out_dir.exists() and any(out_dir.iterdir()) and not args.force:
        raise RuntimeError(f"Output directory exists and is not empty: {out_dir}. Use --force to overwrite files.")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plots").mkdir(parents=True, exist_ok=True)

    df = _prepare_score_matrix(Path(args.score_matrix))
    sample = build_uniform_sample(df, args.seed)
    split = assign_splits(sample, args.seed)
    split.to_csv(out_dir / "splits.csv", index=False)
    split.to_csv(out_dir / "manifest_150.csv", index=False)

    model = train_logreg(split, args.c, args.max_iter)
    calibration = fit_bigauss(split, model)
    scored = apply_bigauss(split, model, calibration)
    scored[scored["bigauss_split"].eq("test_bigauss")].to_csv(out_dir / "test_scored.csv", index=False)
    scored.to_csv(out_dir / "all_scored.csv", index=False)

    artifact = {
        "model": model,
        "feature_cols": FEATURE_COLS,
        "detectors": DETECTORS,
        "bigauss": {
            "variant": "EER",
            "eer": calibration["eer"],
            "eer_for_sigma": calibration["eer_for_sigma"],
            "sigma": calibration["sigma"],
            "mu0": calibration["mu0"],
            "mu1": calibration["mu1"],
            "z_values": calibration["z_values"],
            "cdf_values": calibration["cdf_values"],
        },
    }
    joblib.dump(artifact, out_dir / "model_bigauss.joblib")

    report = make_reports(scored, model, calibration, out_dir)
    _write_json(out_dir / "report.json", _stringify_keys(report))
    write_markdown_report(out_dir / "report.md", report)
    print(json.dumps(_stringify_keys(report["overall"]), indent=2, sort_keys=True))
    print(out_dir / "report.md")


if __name__ == "__main__":
    main()
