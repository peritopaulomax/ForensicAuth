"""Deteccao de copia-cola via PCA (Popescu & Farid 2004 / Peritus INC)."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Tuple, TypeVar

import cv2
import numpy as np

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.copy_move_pca import CopyMovePcaParams, estimate_memory_bytes, run_copy_move_pca
from core.progress import pop_progress_callback, ProgressCallback, report_progress

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


def _compose_alpha_overlay(original_bgr: np.ndarray, bgra: np.ndarray) -> np.ndarray:
    """Blend BGRA detection layer over original (Peritus alpha mask mode)."""
    if bgra.shape[2] != 4:
        return original_bgr
    alpha = bgra[:, :, 3:4].astype(np.float32) / 255.0
    fg = bgra[:, :, :3].astype(np.float32)
    bg = original_bgr.astype(np.float32)
    out = fg * alpha + bg * (1.0 - alpha)
    return np.clip(out, 0, 255).astype(np.uint8)


class CopyMovePcaPlugin(ForensicPlugin):
    """Detect internal copy-move forgeries via PCA + lexicographic block matching."""

    @property
    def name(self) -> str:
        return "copy_move_pca"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        b = int(parameters.get("b", 7))
        if not (3 <= b <= 21):
            return False, "b (block size) deve estar entre 3 e 21"
        n_comp = float(parameters.get("n_comp", 0.75))
        if not (0.0 < n_comp <= 1.0):
            return False, "n_comp deve estar entre 0 e 1"
        nn = int(parameters.get("nn", 2))
        if not (2 <= nn <= 15):
            return False, "nn (search depth) deve estar entre 2 e 15"
        q = int(parameters.get("q", 256))
        if not (64 <= q <= 256):
            return False, "q (quantization) deve estar entre 64 e 256"
        nf = int(parameters.get("nf", 128))
        if nf < 1:
            return False, "nf (min clone size) deve ser >= 1"
        nd = int(parameters.get("nd", 16))
        if nd < 1:
            return False, "nd (min clone distance) deve ser >= 1"
        max_side = int(parameters.get("max_side", 0))
        if max_side < 0:
            return False, "max_side invalido (0 = sem limite)"
        region = parameters.get("region")
        if region is not None:
            if not isinstance(region, (list, tuple)) or len(region) != 4:
                return False, "region deve ser [x, y, w, h]"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        try:
            report_progress(on_progress, 5, "Carregando imagem")
            im_bgr = cv2.imread(evidence_path)
            if im_bgr is None:
                return {"success": False, "error": "Falha ao carregar imagem", "adapter": "copy_move_pca"}

            params = CopyMovePcaParams.from_dict(parameters)
            gray = cv2.cvtColor(im_bgr, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape[:2]

            if params.region is not None:
                x, y, rw, rh = params.region
                work_h, work_w = rh, rw
            else:
                work_h, work_w = h, w
            mem_est = estimate_memory_bytes(work_h, work_w, params.b)
            if params.mem_budget_bytes > 0 and mem_est > params.mem_budget_bytes:
                return {
                    "success": False,
                    "error": (
                        f"Imagem/regiao grande demais (~{mem_est / 1e9:.2f} GB estimados). "
                        f"Limite configurado: {params.mem_budget_bytes / 1e9:.2f} GB."
                    ),
                    "adapter": "copy_move_pca",
                }

            report_progress(on_progress, 8, f"Imagem {w}x{h} px — Copy-Move PCA")

            def _run() -> dict:
                return run_copy_move_pca(
                    gray,
                    params,
                    on_progress=lambda pct, msg: report_progress(on_progress, pct, msg),
                )

            result = _run_blocking_with_heartbeat(
                on_progress,
                start_pct=10,
                end_pct=92,
                base_message="Copy-Move PCA",
                fn=_run,
            )

            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            result_dir = job_artifact_dir(parameters, fallback_subdir="copy_move_pca_tmp")
            paths = {
                "original": result_dir / f"original_{stamp}.png",
                "mask": result_dir / f"mask_{stamp}.png",
                "colored": result_dir / f"colored_{stamp}.png",
                "overlay": result_dir / f"overlay_{stamp}.png",
            }

            cv2.imwrite(str(paths["original"]), im_bgr)
            cv2.imwrite(str(paths["mask"]), result["mask"])

            colored = result["colored_bgr"]
            cv2.imwrite(str(paths["colored"]), colored)

            if params.alpha_mask and result.get("bgra_overlay") is not None:
                overlay = _compose_alpha_overlay(im_bgr, result["bgra_overlay"])
            else:
                overlay = cv2.addWeighted(im_bgr, 0.55, colored, 0.45, 0)
            cv2.imwrite(str(paths["overlay"]), overlay)

            mask_area = int(np.count_nonzero(result["mask"]))
            mask_ratio = float(mask_area / (h * w)) if h * w else 0.0

            report_progress(on_progress, 100, "Copy-Move PCA concluido")

            return {
                "success": True,
                "adapter": "copy_move_pca",
                "status": "completed",
                "clone_regions_detected": result["clone_regions_detected"],
                "clone_displacements_raw": result.get("clone_displacements_raw", 0),
                "mask_area_pixels": mask_area,
                "mask_ratio": mask_ratio,
                "memory_estimate_bytes": result["memory_estimate_bytes"],
                "prep_meta": result.get("prep_meta", {}),
                "parameters": result["parameters"],
                "original_crop_path": str(paths["original"]),
                "mask_image_path": str(paths["mask"]),
                "colored_overlay_image_path": str(paths["colored"]),
                "overlay_image_path": str(paths["overlay"]),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except MemoryError as exc:
            return {"success": False, "error": str(exc), "adapter": "copy_move_pca"}
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "copy_move_pca"}
