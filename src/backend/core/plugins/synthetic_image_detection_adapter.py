"""Adapter — detecção de imagens sintéticas (ensemble CNN + FFT + Effort)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from PIL import Image

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.synthetic_image_detection.pipeline import (
    _as_rgb,
    run_synthetic_image_detection_analysis,
)
from core.legacy.synthetic_image_detection.runtime import runtime_status
from core.progress import pop_progress_callback, report_progress
from core.technique_ids import SYNTHETIC_IMAGE_DETECTION

_SCORE_HEADERS = ("Modelo", "Score AI", "Score Real", "Razão (Log)", "Classificação", "Dispositivo")


def _write_model_scores_txt(out_dir: Path, rows: list[list[str]]) -> Path:
    """Relatório tabulado dos escores por modelo (artefato principal para derivados)."""
    lines = ["\t".join(_SCORE_HEADERS)]
    for row in rows:
        lines.append("\t".join(str(cell) for cell in row))
    path = out_dir / "model_scores.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class SyntheticImageDetectionAdapter(ForensicPlugin):
    """Ensemble ai-image-detector, sdxl-flux-detector, XGBoost (FFT) e Effort."""

    @property
    def name(self) -> str:
        return SYNTHETIC_IMAGE_DETECTION

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    @classmethod
    def is_runtime_available(cls) -> Tuple[bool, str]:
        return runtime_status()

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        ok, reason = runtime_status()
        if not ok:
            return False, reason
        mode = parameters.get("mode", "full")
        if mode not in ("full", "fast"):
            return False, "mode deve ser 'full' ou 'fast'"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        ok, reason = runtime_status()
        if not ok:
            return {
                "success": False,
                "error": reason,
                "adapter": SYNTHETIC_IMAGE_DETECTION,
                "status": "unavailable",
            }

        try:
            report_progress(on_progress, 2, "Carregando evidencia")
            image = _as_rgb(Image.open(evidence_path))
            image.load()

            generate_visuals = bool(parameters.get("generate_visuals", True))
            mode = str(parameters.get("mode", "full"))
            if mode == "fast":
                generate_visuals = False

            analysis = run_synthetic_image_detection_analysis(
                image,
                generate_visuals=generate_visuals,
                on_progress=on_progress,
            )

            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            out_dir = job_artifact_dir(parameters, fallback_subdir="synthetic_image_detection_tmp")
            report_progress(on_progress, 88, "Salvando artefatos e relatorio…")

            def save_pil(img: Image.Image | None, filename: str) -> str | None:
                if img is None:
                    return None
                path = out_dir / f"{filename}_{stamp}.png"
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.save(path, format="PNG")
                return str(path)

            report_progress(on_progress, 94, "Gravando model_scores.txt…")
            scores_path = _write_model_scores_txt(out_dir, analysis["individual_results"])

            result: Dict[str, Any] = {
                "success": True,
                "adapter": SYNTHETIC_IMAGE_DETECTION,
                "status": "completed",
                "mode": mode,
                "generate_visuals": generate_visuals,
                "inference_device": analysis.get("inference_device", "cpu"),
                "individual_results": analysis["individual_results"],
                "model_scores_txt_path": str(scores_path),
                "model_scores_filename": "model_scores.txt",
                "input_image_path": save_pil(analysis.get("input_image"), "input_image"),
                "input_fft_image_path": save_pil(analysis.get("input_fft"), "input_fft"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            visual_map = {
                "nlm_residue_image_path": "nlm_residue",
                "median_residue_image_path": "median_residue",
                "nlm_fft_image_path": "nlm_fft",
                "median_fft_image_path": "median_fft",
            }
            for result_key, analysis_key in visual_map.items():
                saved = save_pil(analysis.get(analysis_key), analysis_key)
                if saved:
                    result[result_key] = saved

            report_progress(on_progress, 100, "Concluido")
            return result

        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": SYNTHETIC_IMAGE_DETECTION}
