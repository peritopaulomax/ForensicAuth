"""PoC — ensemble calibrado com scores fantasma (demo_ensemble_lr)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve

from core.reference_data.paths import get_reference_data_root

ProgressCb = Callable[[int, str], None] | None

FEATURE_MAP = {"detector_a": "score_a", "detector_b": "score_b"}
SCORES_REL = Path("features/scores/scores.csv")


def _progress(cb: ProgressCb, pct: int, msg: str) -> None:
    if cb:
        cb(pct, msg)


def _score_questioned(evidence_path: str, selected: list[str]) -> dict[str, float]:
    """Detectores toy: estatísticas da imagem (não forense)."""
    img = Image.open(evidence_path).convert("L")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    mean = float(arr.mean())
    std = float(arr.std() + 1e-6)
    raw = {
        "detector_a": float(np.clip(mean, 0.01, 0.99)),
        "detector_b": float(np.clip(0.5 + (std - 0.15), 0.01, 0.99)),
    }
    return {k: raw[k] for k in selected if k in raw}


def _load_population(domain: str) -> pd.DataFrame:
    path = get_reference_data_root() / domain / SCORES_REL
    if not path.is_file():
        raise FileNotFoundError(f"CSV de scores não encontrado: {path}")
    df = pd.read_csv(path)
    need = {"base_group", "subgroup", "label", "split", "score_a", "score_b"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"CSV sem colunas {sorted(missing)}")
    return df


def _filter_pop(df: pd.DataFrame, items: list[dict[str, str]]) -> pd.DataFrame:
    keys = {(str(i["base_group"]), str(i["subgroup"])) for i in items if i.get("base_group")}
    if not keys:
        return df.iloc[0:0].copy()
    mask = df.apply(lambda r: (str(r["base_group"]), str(r["subgroup"])) in keys, axis=1)
    return df.loc[mask].copy()


def _eer(y_real: np.ndarray, scores: np.ndarray) -> float:
    fpr, tpr, _ = roc_curve(y_real, scores)
    fnr = 1.0 - tpr
    idx = int(np.nanargmin(np.abs(fpr - fnr)))
    return float((fpr[idx] + fnr[idx]) / 2.0)


def _bigauss_params(z: np.ndarray, y_real: np.ndarray) -> dict[str, float]:
    from scipy.stats import norm

    eer = _eer(y_real, z)
    sigma = float(-2.0 * norm.ppf(float(np.clip(eer, 1e-6, 0.499999))))
    return {
        "eer": eer,
        "sigma": sigma,
        "mu_fake": float(-(sigma**2) / 2.0),
        "mu_real": float((sigma**2) / 2.0),
    }


def _log10_lr_from_z(z: float, bg: dict[str, float]) -> tuple[float, float]:
    from scipy.stats import norm

    sigma = bg["sigma"]
    # densidade sob H1=real vs H0=fake
    p_h1 = float(norm.pdf(z, bg["mu_real"], sigma) + 1e-300)
    p_h0 = float(norm.pdf(z, bg["mu_fake"], sigma) + 1e-300)
    lr = p_h1 / p_h0
    return float(np.log10(lr)), float(lr)


def _plot_tippett(path: Path, log10_lr: np.ndarray, y_real: np.ndarray) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fake = np.sort(log10_lr[y_real == 0])
    real = np.sort(log10_lr[y_real == 1])
    plt.figure(figsize=(8, 5))
    if len(fake):
        plt.step(fake, 1.0 - np.arange(len(fake)) / len(fake), where="post", color="red", label="H0")
    if len(real):
        plt.step(real, np.arange(1, len(real) + 1) / len(real), where="post", color="blue", label="H1")
    plt.axvline(0, color="black", ls="--", lw=1)
    plt.xlabel("log10 LR")
    plt.ylabel("Proporção")
    plt.title("Tippett (PoC demo)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def _plot_hist(path: Path, log10_lr: np.ndarray, y_real: np.ndarray, q: float | None) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.figure(figsize=(8, 5))
    plt.hist(log10_lr[y_real == 0], bins=20, alpha=0.6, color="red", label="fake")
    plt.hist(log10_lr[y_real == 1], bins=20, alpha=0.6, color="blue", label="real")
    if q is not None and np.isfinite(q):
        plt.axvline(q, color="black", ls="--", lw=2, label="questionado")
    plt.legend()
    plt.title("Distribuição log10 LR (PoC)")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def _plot_identity(path: Path, z: np.ndarray, log10_lr: np.ndarray) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.figure(figsize=(6, 6))
    plt.scatter(z, log10_lr, s=12, alpha=0.7)
    plt.xlabel("logit LogReg (z)")
    plt.ylabel("log10 LR calibrada")
    plt.title("Identidade z → LR (PoC)")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def run(
    evidence_path: str,
    parameters: dict[str, Any],
    out_dir: Path,
    *,
    on_progress: ProgressCb = None,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    selected = list(parameters.get("selected_analyses") or [])
    if not selected:
        return {"success": False, "error": "selected_analyses vazio", "adapter": "demo_ensemble_scores"}

    domain = str(parameters.get("reference_lr_domain") or "demo_ensemble_lr")
    lr_enabled = bool(parameters.get("reference_lr_enabled", True))

    _progress(on_progress, 10, "Scores do questionado")
    q_scores = _score_questioned(evidence_path, selected)
    if not q_scores:
        return {"success": False, "error": "nenhum detector válido selecionado", "adapter": "demo_ensemble_scores"}

    feat_cols = [FEATURE_MAP[d] for d in selected if d in FEATURE_MAP]
    # map detector → column for questioned vector
    q_vec = np.array([q_scores[d] for d in selected if d in FEATURE_MAP], dtype=float).reshape(1, -1)

    rows = []
    for d in selected:
        s = q_scores.get(d, float("nan"))
        rows.append([d, f"{s:.4f}", f"{1.0 - s:.4f}", "—", "—", "CPU"])

    txt = out_dir / "model_scores.txt"
    txt.write_text("\n".join(f"{r[0]}\t{r[1]}" for r in rows) + "\n", encoding="utf-8")

    result: dict[str, Any] = {
        "success": True,
        "adapter": "demo_ensemble_scores",
        "individual_results": rows,
        "score_positive": float(np.mean(list(q_scores.values()))),
        "score_negative": float(1.0 - np.mean(list(q_scores.values()))),
        "label": "demo",
        "model_scores_txt_path": str(txt),
        "note": "PoC: tipicidade/aug ignorados nesta versão.",
    }

    if not lr_enabled:
        _progress(on_progress, 100, "OK (sem LR)")
        return result

    _progress(on_progress, 30, "Carregar população")
    try:
        df = _load_population(domain)
    except Exception as exc:
        return {**result, "success": False, "error": str(exc)}

    pop = parameters.get("reference_population") or {}
    fit_items = pop.get("fit_items") or pop.get("items") or []
    test_items = pop.get("test_items") or pop.get("items") or []
    fit_df = _filter_pop(df, fit_items)
    test_df = _filter_pop(df, test_items)
    train = fit_df[fit_df["split"] == "train"]
    val = fit_df[fit_df["split"] == "val"]
    test = test_df[test_df["split"] == "test"]

    if len(train) < 4 or len(val) < 2 or len(test) < 2:
        return {
            **result,
            "success": False,
            "error": f"splits insuficientes (train={len(train)}, val={len(val)}, test={len(test)})",
        }

    _progress(on_progress, 50, "LogReg + bigaussian")
    X_train = train[feat_cols].to_numpy(dtype=float)
    y_train = train["label"].astype(int).to_numpy()  # 1=real
    model = LogisticRegression(max_iter=2000, random_state=42)
    model.fit(X_train, y_train)

    def decision_z(X: np.ndarray) -> np.ndarray:
        if hasattr(model, "decision_function"):
            return model.decision_function(X).astype(float)
        proba = model.predict_proba(X)[:, 1]
        return np.log(proba / (1.0 - proba + 1e-12)).astype(float)

    z_val = decision_z(val[feat_cols].to_numpy(dtype=float))
    y_val = val["label"].astype(int).to_numpy()
    bg = _bigauss_params(z_val, y_val)

    z_test = decision_z(test[feat_cols].to_numpy(dtype=float))
    y_test = test["label"].astype(int).to_numpy()
    log10_list, lr_list = [], []
    for zi in z_test:
        l10, lr = _log10_lr_from_z(float(zi), bg)
        log10_list.append(l10)
        lr_list.append(lr)
    log10_arr = np.array(log10_list, dtype=float)

    try:
        auc = float(roc_auc_score(y_test, z_test))
    except ValueError:
        auc = float("nan")
    eer_test = _eer(y_test, z_test)

    z_q = float(decision_z(q_vec)[0])
    q_log10, q_lr = _log10_lr_from_z(z_q, bg)

    _progress(on_progress, 80, "Gravar plots LR")
    tippett = out_dir / "lr_reference_tippett.png"
    dist = out_dir / "lr_reference_distribution.png"
    ident = out_dir / "lr_reference_identity.png"
    _plot_tippett(tippett, log10_arr, y_test)
    _plot_hist(dist, log10_arr, y_test, q_log10)
    _plot_identity(ident, z_test, log10_arr)

    result["reference_lr"] = {
        "success": True,
        "hypothesis_positive": "real",
        "hypothesis_negative": "fake",
        "selected_count": len({(i.get("base_group"), i.get("subgroup")) for i in fit_items + test_items}),
        "fit_count": len(fit_items),
        "test_count": len(test_items),
        "split_roles_separated": True,
        "fit_sample_rows": int(len(fit_df)),
        "test_sample_rows": int(len(test)),
        "sample_rows": int(len(fit_df) + len(test_df)),
        "test_metrics": {
            "rows": int(len(test)),
            "real_rows": int((y_test == 1).sum()),
            "fake_rows": int((y_test == 0).sum()),
            "auc": auc,
            "eer": eer_test,
            "cllr": None,
            "min_cllr": None,
        },
        "bigauss": bg,
        "questioned": {"log10_lr": q_log10, "lr": q_lr, "logreg_z": z_q},
        "meta_classifier": str(parameters.get("meta_classifier") or "logistic"),
        "note": "PoC demo_ensemble_lr ",
        "latent_typicality": False,
        "augmented_reference": False,
    }
    result["lr_reference_tippett_path"] = str(tippett)
    result["lr_reference_distribution_path"] = str(dist)
    result["lr_reference_identity_path"] = str(ident)

    _progress(on_progress, 100, "PoC concluída")
    return result