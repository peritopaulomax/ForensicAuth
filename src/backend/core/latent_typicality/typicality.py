"""k-NN typicality features from detector embeddings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import joblib
import numpy as np
from sklearn.neighbors import NearestNeighbors

DistanceMetric = Literal["cosine", "euclidean"]


@dataclass
class TypicalityReference:
    detector: str
    distance: DistanceMetric
    k: int
    knn_real: NearestNeighbors
    knn_synthetic: NearestNeighbors
    radii_real: np.ndarray
    radii_synthetic: np.ndarray
    real_embeddings: np.ndarray
    synthetic_embeddings: np.ndarray
    real_ids: list[str]
    synthetic_ids: list[str]
    radii_real_sorted: np.ndarray | None = None
    radii_synthetic_sorted: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.radii_real_sorted is None:
            self.radii_real_sorted = np.sort(self.radii_real)
        if self.radii_synthetic_sorted is None:
            self.radii_synthetic_sorted = np.sort(self.radii_synthetic)


def _prepare_embeddings(embeddings: np.ndarray, distance: DistanceMetric) -> np.ndarray:
    x = np.asarray(embeddings, dtype=np.float64)
    if distance == "cosine":
        norms = np.linalg.norm(x, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-12)
        return x / norms
    return x


def _kth_neighbor_distance(
    knn: NearestNeighbors,
    query: np.ndarray,
    *,
    k: int,
    exclude_self: bool,
) -> float:
    return float(
        _kth_neighbor_distances_batch(
            knn,
            query.reshape(1, -1),
            k=k,
            exclude_self=exclude_self,
        )[0]
    )


def _kth_neighbor_distances_batch(
    knn: NearestNeighbors,
    queries: np.ndarray,
    *,
    k: int,
    exclude_self: bool | np.ndarray,
) -> np.ndarray:
    queries = np.asarray(queries, dtype=np.float64)
    if queries.ndim == 1:
        queries = queries.reshape(1, -1)
    n_rows = len(queries)
    if isinstance(exclude_self, np.ndarray):
        exclude_self = exclude_self.astype(bool, copy=False)
        if exclude_self.shape != (n_rows,):
            raise ValueError("exclude_self mask must match number of queries")
        out = np.empty(n_rows, dtype=np.float64)
        if exclude_self.any():
            idx = np.flatnonzero(exclude_self)
            out[idx] = _kth_neighbor_distances_batch(
                knn, queries[idx], k=k, exclude_self=True
            )
        if (~exclude_self).any():
            idx = np.flatnonzero(~exclude_self)
            out[idx] = _kth_neighbor_distances_batch(
                knn, queries[idx], k=k, exclude_self=False
            )
        return out

    n_neighbors = min(k + 1 if exclude_self else k, knn.n_samples_fit_)
    distances, _ = knn.kneighbors(queries, n_neighbors=n_neighbors)
    if not exclude_self:
        return distances[:, k - 1].astype(np.float64, copy=False)

    # Vetorizado: quando o vizinho 0 é o próprio ponto (dist≈0), o k-ésimo fica na coluna k.
    has_self = (distances[:, 0] <= 1e-12) & (distances.shape[1] > 1)
    k_col = distances[:, min(k, distances.shape[1] - 1)]
    k_minus_col = distances[:, min(k - 1, distances.shape[1] - 1)]
    return np.where(has_self, k_col, k_minus_col).astype(np.float64, copy=False)


def build_typicality_reference(
    *,
    detector: str,
    distance: DistanceMetric,
    k: int,
    real_embeddings: np.ndarray,
    synthetic_embeddings: np.ndarray,
    real_ids: list[str],
    synthetic_ids: list[str],
) -> TypicalityReference:
    if len(real_embeddings) < max(k + 1, 2) or len(synthetic_embeddings) < max(k + 1, 2):
        raise RuntimeError(f"Referência insuficiente para detector={detector}, k={k}")

    metric = "cosine" if distance == "cosine" else "euclidean"
    x_real = _prepare_embeddings(real_embeddings, distance)
    x_spoof = _prepare_embeddings(synthetic_embeddings, distance)

    knn_real = NearestNeighbors(metric=metric, algorithm="auto")
    knn_spoof = NearestNeighbors(metric=metric, algorithm="auto")
    knn_real.fit(x_real)
    knn_spoof.fit(x_spoof)

    radii_real = _kth_neighbor_distances_batch(knn_real, x_real, k=k, exclude_self=True)
    radii_synthetic = _kth_neighbor_distances_batch(knn_spoof, x_spoof, k=k, exclude_self=True)

    return TypicalityReference(
        detector=detector,
        distance=distance,
        k=k,
        knn_real=knn_real,
        knn_synthetic=knn_spoof,
        radii_real=radii_real,
        radii_synthetic=radii_synthetic,
        real_embeddings=x_real,
        synthetic_embeddings=x_spoof,
        real_ids=list(real_ids),
        synthetic_ids=list(synthetic_ids),
        radii_real_sorted=np.sort(radii_real),
        radii_synthetic_sorted=np.sort(radii_synthetic),
    )


def _empirical_cdf(values_sorted: np.ndarray, query: float) -> float:
    return float(_empirical_cdf_batch(values_sorted, np.asarray([query], dtype=np.float64))[0])


def _empirical_cdf_batch(values_sorted: np.ndarray, queries: np.ndarray) -> np.ndarray:
    denom = max(len(values_sorted), 1)
    return np.searchsorted(values_sorted, np.asarray(queries, dtype=np.float64), side="right") / denom


def typicality_features_batch(
    embeddings: np.ndarray,
    ref: TypicalityReference,
    *,
    eps: float = 1e-8,
    exclude_self: bool | np.ndarray = False,
) -> dict[str, np.ndarray]:
    x = _prepare_embeddings(np.asarray(embeddings, dtype=np.float64), ref.distance)
    r_real = _kth_neighbor_distances_batch(ref.knn_real, x, k=ref.k, exclude_self=exclude_self)
    r_spoof = _kth_neighbor_distances_batch(
        ref.knn_synthetic, x, k=ref.k, exclude_self=exclude_self
    )

    assert ref.radii_real_sorted is not None
    assert ref.radii_synthetic_sorted is not None
    p_real = _empirical_cdf_batch(ref.radii_real_sorted, r_real)
    p_spoof = _empirical_cdf_batch(ref.radii_synthetic_sorted, r_spoof)
    t_real = 1.0 - p_real
    t_spoof = 1.0 - p_spoof
    ood = 1.0 - np.maximum(t_real, t_spoof)
    delta_r = r_real - r_spoof
    rho = np.log((r_real + eps) / (r_spoof + eps))

    prefix = ref.detector
    return {
        f"T_R_{prefix}": t_real,
        f"T_S_{prefix}": t_spoof,
        f"OOD_{prefix}": ood,
        f"Delta_r_{prefix}": delta_r,
        f"rho_{prefix}": rho,
        f"r_R_{prefix}": r_real,
        f"r_S_{prefix}": r_spoof,
    }


def typicality_features_for_embedding(
    embedding: np.ndarray,
    ref: TypicalityReference,
    *,
    eps: float = 1e-8,
    exclude_self: bool = False,
) -> dict[str, float]:
    x = _prepare_embeddings(np.asarray(embedding, dtype=np.float64).reshape(1, -1), ref.distance)[0]
    r_real = _kth_neighbor_distance(ref.knn_real, x, k=ref.k, exclude_self=exclude_self)
    r_spoof = _kth_neighbor_distance(ref.knn_synthetic, x, k=ref.k, exclude_self=exclude_self)

    assert ref.radii_real_sorted is not None
    assert ref.radii_synthetic_sorted is not None
    p_real = _empirical_cdf(ref.radii_real_sorted, r_real)
    p_spoof = _empirical_cdf(ref.radii_synthetic_sorted, r_spoof)
    t_real = 1.0 - p_real
    t_spoof = 1.0 - p_spoof
    ood = 1.0 - max(t_real, t_spoof)
    delta_r = r_real - r_spoof
    rho = float(np.log((r_real + eps) / (r_spoof + eps)))

    prefix = ref.detector
    return {
        f"T_R_{prefix}": t_real,
        f"T_S_{prefix}": t_spoof,
        f"OOD_{prefix}": ood,
        f"Delta_r_{prefix}": delta_r,
        f"rho_{prefix}": rho,
        f"r_R_{prefix}": r_real,
        f"r_S_{prefix}": r_spoof,
    }


def save_typicality_reference(ref: TypicalityReference, out_dir) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(ref.knn_real, out_dir / f"knn_real_{ref.detector}.joblib")
    joblib.dump(ref.knn_synthetic, out_dir / f"knn_synthetic_{ref.detector}.joblib")
    np.save(out_dir / f"radii_real_{ref.detector}.npy", ref.radii_real)
    np.save(out_dir / f"radii_synthetic_{ref.detector}.npy", ref.radii_synthetic)
