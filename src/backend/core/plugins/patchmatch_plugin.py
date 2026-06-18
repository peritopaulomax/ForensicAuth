"""Deteccao de copia-cola via PatchMatch (Ehret 2018)."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Tuple, TypeVar

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from app.config import get_settings
from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.progress import pop_progress_callback, ProgressCallback, report_progress
from core.legacy.patchmatch import patchmatch as pm
from core.legacy.patchmatch import postprocessing as pp

T = TypeVar("T")


def _format_elapsed(seconds: float) -> str:
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    if minutes:
        return f"{minutes} min {secs}s"
    return f"{secs}s"


def _run_blocking_with_heartbeat(
    on_progress: ProgressCallback | None,
    *,
    start_pct: int,
    end_pct: int,
    base_message: str,
    fn: Callable[[], T],
    interval_sec: float = 5.0,
) -> T:
    """Executa etapa bloqueante reportando tempo decorrido enquanto aguarda."""
    result_holder: list[T] = []
    error_holder: list[BaseException] = []
    done = threading.Event()
    started = time.monotonic()

    def worker() -> None:
        try:
            result_holder.append(fn())
        except BaseException as exc:
            error_holder.append(exc)
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    tick = 0
    span = max(1, end_pct - start_pct)
    while not done.wait(timeout=interval_sec):
        tick += 1
        elapsed = time.monotonic() - started
        pct = start_pct + min(span - 1, tick)
        report_progress(
            on_progress,
            pct,
            f"{base_message} ({_format_elapsed(elapsed)} decorridos)",
        )

    thread.join()
    if error_holder:
        raise error_holder[0]
    return result_holder[0]


def _color_by_displacement(
    im_rgb: np.ndarray, mask: np.ndarray, vect_field: np.ndarray
) -> np.ndarray:
    """Tint masked pixels by quantized displacement — same vector ≈ same color."""
    out = im_rgb.copy().astype(np.float32)
    if not np.any(mask):
        return out

    di = vect_field[..., 0]
    dj = vect_field[..., 1]
    sig_i = np.round(di / 4.0).astype(np.int32)
    sig_j = np.round(dj / 4.0).astype(np.int32)

    palette = plt.cm.tab20(np.linspace(0, 1, 20))[:, :3] * 255.0
    signature_color: Dict[Tuple[int, int], np.ndarray] = {}
    colored = np.zeros_like(out)

    ys, xs = np.where(mask)
    for y, x in zip(ys, xs):
        key = (int(sig_i[y, x]), int(sig_j[y, x]))
        if key not in signature_color:
            signature_color[key] = palette[len(signature_color) % len(palette)]
        colored[y, x] = signature_color[key]

    out[mask] = 0.42 * out[mask] + 0.58 * colored[mask]
    return out


def _render_displacement_arrows(
    im_rgb: np.ndarray,
    mask: np.ndarray,
    vect_field: np.ndarray,
    max_arrows: int = 400,
) -> np.ndarray:
    """Draw subsampled arrows from source to destination (copy-move pairing)."""
    vis = im_rgb.copy().astype(np.uint8)
    h, w = mask.shape
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return vis

    step = max(1, len(xs) // max_arrows)
    for idx in range(0, len(xs), step):
        y, x = int(ys[idx]), int(xs[idx])
        di = int(vect_field[y, x, 0])
        dj = int(vect_field[y, x, 1])
        if di == 0 and dj == 0:
            continue
        x2 = x + dj
        y2 = y + di
        if 0 <= x2 < w and 0 <= y2 < h:
            cv2.arrowedLine(
                vis,
                (x, y),
                (x2, y2),
                (0, 255, 255),
                thickness=1,
                tipLength=0.25,
                line_type=cv2.LINE_AA,
            )
    return vis


def _render_component_heatmap(field: np.ndarray) -> np.ndarray:
    """Mapa de calor em escala de cinza de um componente do campo vetorial."""
    f = field.astype(np.float64)
    fmin, fmax = float(np.min(f)), float(np.max(f))
    span = fmax - fmin or 1.0
    u8 = ((f - fmin) / span * 255).astype(np.uint8)
    return cv2.applyColorMap(u8, cv2.COLORMAP_MAGMA)


class PatchMatchPlugin(ForensicPlugin):
    """Detect internal copy-move forgeries via PatchMatch + Zernike moments."""

    @property
    def name(self) -> str:
        return "patchmatch"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        p = int(parameters.get("p", 10))
        if p < 2:
            return False, "p (meio-tamanho do patch) deve ser >= 2"
        min_dn = int(parameters.get("min_dn", 64))
        if min_dn < 1:
            return False, "min_dn deve ser >= 1"
        iterations = int(parameters.get("iterations", 5))
        if not (1 <= iterations <= 20):
            return False, "iterations deve estar entre 1 e 20"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        try:
            report_progress(on_progress, 8, "Carregando imagem")
            im_bgr = cv2.imread(evidence_path)
            if im_bgr is None:
                return {"success": False, "error": "Falha ao carregar imagem", "adapter": "patchmatch"}

            im_rgb = cv2.cvtColor(im_bgr, cv2.COLOR_BGR2RGB).astype(np.float64)
            m, n = im_rgb.shape[:2]

            p = int(parameters.get("p", 10))
            max_zrd = int(parameters.get("max_zrd", 6))
            min_dn = int(parameters.get("min_dn", 64))
            n_rs_candidates = int(parameters.get("n_rs_candidates", 5))
            iterations = int(parameters.get("iterations", 5))
            min_region_size = int(parameters.get("min_region_size", 128))
            zernike = bool(parameters.get("zernike", True))
            max_arrows = int(parameters.get("max_arrows", 400))

            if min(m, n) < 2 * p + 1:
                return {
                    "success": False,
                    "error": f"Imagem pequena demais para p={p}. Minimo: {2 * p + 1}px por lado.",
                    "adapter": "patchmatch",
                }

            report_progress(on_progress, 12, f"Imagem {n}×{m} px — preparando PatchMatch")
            zernike_label = "Zernike" if zernike else "sem Zernike"
            report_progress(
                on_progress,
                14,
                f"Inicializando ({zernike_label}): filtros, momentos e dist_field — etapa mais lenta",
            )
            matcher = _run_blocking_with_heartbeat(
                on_progress,
                start_pct=15,
                end_pct=24,
                base_message=f"Inicializando PatchMatch ({zernike_label})",
                fn=lambda: pm.PatchMatch(
                    im_rgb,
                    p=p,
                    max_zrd=max_zrd,
                    min_dn=min_dn,
                    n_rs_candidates=n_rs_candidates,
                    init_method=2,
                    zernike=zernike,
                ),
            )
            report_progress(on_progress, 25, "PatchMatch inicializado — iniciando iteracoes")

            for i in range(iterations):
                pct = 25 + int(44 * (i + 1) / max(iterations, 1))
                report_progress(on_progress, pct, f"PatchMatch — iteracao {i + 1}/{iterations}")
                matcher.iterate()

            report_progress(on_progress, 70, "Iteracoes PatchMatch concluidas")
            report_progress(on_progress, 72, "Pos-processamento (mascara)")

            mask = pp.compute_mask_1(matcher.vect_field, matcher.m, matcher.n, matcher.p, min_region_size)
            mask_area = int(np.sum(mask))
            mask_ratio = float(mask_area / (m * n))
            n_displacement_groups = len(
                {
                    (int(np.round(matcher.vect_field[y, x, 0] / 4)),
                     int(np.round(matcher.vect_field[y, x, 1] / 4)))
                    for y, x in zip(*np.where(mask))
                }
            )

            settings = get_settings()
            result_dir = job_artifact_dir(parameters, fallback_subdir="patchmatch_tmp")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

            report_progress(on_progress, 78, "Gerando visualizacoes")
            report_progress(on_progress, 92, "Salvando artefatos PNG")
            paths = {
                "original": result_dir / f"original_{stamp}.png",
                "mask": result_dir / f"mask_{stamp}.png",
                "overlay": result_dir / f"overlay_{stamp}.png",
                "colored": result_dir / f"colored_{stamp}.png",
                "vectors": result_dir / f"vectors_{stamp}.png",
                "dist": result_dir / f"dist_{stamp}.png",
                "vect_i": result_dir / f"vect_i_{stamp}.png",
                "vect_j": result_dir / f"vect_j_{stamp}.png",
            }

            cv2.imwrite(str(paths["original"]), im_bgr)
            cv2.imwrite(str(paths["mask"]), (mask.astype(np.uint8) * 255))

            overlay = im_rgb.copy()
            overlay[mask] = overlay[mask] * 0.4 + np.array([255.0, 64.0, 64.0]) * 0.6
            cv2.imwrite(str(paths["overlay"]), cv2.cvtColor(overlay.astype(np.uint8), cv2.COLOR_RGB2BGR))

            colored = _color_by_displacement(im_rgb, mask, matcher.vect_field)
            cv2.imwrite(str(paths["colored"]), cv2.cvtColor(colored.astype(np.uint8), cv2.COLOR_RGB2BGR))

            arrows = _render_displacement_arrows(im_rgb, mask, matcher.vect_field, max_arrows=max_arrows)
            cv2.imwrite(str(paths["vectors"]), cv2.cvtColor(arrows, cv2.COLOR_RGB2BGR))

            dist_norm = matcher.dist_field.copy()
            dmax = float(np.max(dist_norm)) or 1.0
            dist_u8 = (255 * (1.0 - dist_norm / dmax)).astype(np.uint8)
            cv2.imwrite(str(paths["dist"]), cv2.applyColorMap(dist_u8, cv2.COLORMAP_VIRIDIS))

            cv2.imwrite(str(paths["vect_i"]), _render_component_heatmap(matcher.vect_field[..., 0]))
            cv2.imwrite(str(paths["vect_j"]), _render_component_heatmap(matcher.vect_field[..., 1]))

            sum_dist = [float(x) for x in matcher.sum_of_distances[: iterations + 1] if x > 0]
            n_prop = [int(x) for x in matcher.n_propagations[:iterations]]

            report_progress(on_progress, 100, "PatchMatch concluido")

            return {
                "success": True,
                "adapter": "patchmatch",
                "status": "completed",
                "mask_area_pixels": mask_area,
                "mask_ratio": mask_ratio,
                "displacement_groups": n_displacement_groups,
                "iterations": iterations,
                "sum_of_distances": sum_dist,
                "n_propagations": n_prop,
                "parameters": {
                    "p": p,
                    "max_zrd": max_zrd,
                    "min_dn": min_dn,
                    "n_rs_candidates": n_rs_candidates,
                    "min_region_size": min_region_size,
                    "zernike": zernike,
                    "max_arrows": max_arrows,
                },
                "original_crop_path": str(paths["original"]),
                "mask_image_path": str(paths["mask"]),
                "overlay_image_path": str(paths["overlay"]),
                "colored_overlay_image_path": str(paths["colored"]),
                "vectors_image_path": str(paths["vectors"]),
                "dist_image_path": str(paths["dist"]),
                "vect_i_image_path": str(paths["vect_i"]),
                "vect_j_image_path": str(paths["vect_j"]),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "patchmatch"}
