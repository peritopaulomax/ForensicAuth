"""Adapter — detecção de imagens sintéticas (ensemble HuggingFace + B-Free + Corvi2023)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
from PIL import Image

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.synthetic_image_detection.pipeline import (
    VALID_SYNTHETIC_ANALYSES,
    _as_rgb,
    run_synthetic_image_detection_analysis,
)
from core.legacy.synthetic_image_detection.runtime import runtime_status
from core.progress import pop_progress_callback, report_progress
from core.latent_typicality.representations_utils import representations_matrix_available
from core.synthetic_lr_reference import (
    AUGMENTATION_MULTIPLIER,
    DEFAULT_REPRESENTATIONS_MATRIX,
    DEFAULT_SCORE_MATRIX,
    DEFAULT_TYPICALITY_DISTANCE,
    DEFAULT_TYPICALITY_K,
    DEFAULT_TYPICALITY_SYSTEM,
    META_CLASSIFIERS,
    compute_reference_lr,
)
from core.technique_ids import SYNTHETIC_IMAGE_DETECTION

_TYPICALITY_SYSTEMS = ("A", "B", "C", "D")
_TYPICALITY_DISTANCES = ("cosine", "euclidean")

_AUGMENTED_SCORE_MATRIX = Path(__file__).resolve().parents[4] / "outputs" / "lr_calibration" / "score_matrices" / "lr_scores_balanced_full_augmented.csv"

_SCORE_HEADERS = ("Modelo", "Score AI", "Score Real", "Razão (Log)", "Classificação", "Dispositivo")


def _detector_scores_for_json(detector_scores: dict[str, Any]) -> dict[str, Any]:
    """Strip non-JSON-serializable embeddings from API payloads."""
    safe: dict[str, Any] = {}
    for detector, scores in (detector_scores or {}).items():
        if not isinstance(scores, dict):
            safe[detector] = scores
            continue
        row = dict(scores)
        embedding = row.pop("embedding", None)
        if embedding is not None:
            row["embedding_dim"] = int(np.asarray(embedding).size)
        safe[detector] = row
    return safe


def _write_model_scores_txt(out_dir: Path, rows: list[list[str]]) -> Path:
    """Relatório tabulado dos escores por modelo (artefato principal para derivados)."""
    lines = ["\t".join(_SCORE_HEADERS)]
    for row in rows:
        lines.append("\t".join(str(cell) for cell in row))
    path = out_dir / "model_scores.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class SyntheticImageDetectionAdapter(ForensicPlugin):
    """Ensemble ai-image-detector, sdxl-flux-detector, B-Free e Corvi2023/CLIP-D."""

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
        selected = parameters.get("selected_analyses")
        if selected is not None:
            if not isinstance(selected, list):
                return False, "selected_analyses deve ser uma lista"
            normalized = {str(item).strip() for item in selected if str(item).strip()}
            if not normalized:
                return False, "Selecione pelo menos uma analise de deteccao sintetica"
            invalid = sorted(normalized - VALID_SYNTHETIC_ANALYSES)
            if invalid:
                return False, "Analises sinteticas invalidas: " + ", ".join(invalid)
        classifier = parameters.get("meta_classifier")
        if classifier is not None and str(classifier).lower().strip() not in META_CLASSIFIERS:
            return False, "meta_classifier deve ser um de: " + ", ".join(META_CLASSIFIERS)
        use_aug = parameters.get("use_augmented_reference")
        if use_aug is not None and not isinstance(use_aug, bool):
            return False, "use_augmented_reference deve ser booleano"
        if use_aug and not _AUGMENTED_SCORE_MATRIX.is_file():
            return False, "Score matrix aumentado nao encontrado; gere as variantes primeiro."
        use_lt = parameters.get("use_latent_typicality")
        if use_lt is not None and not isinstance(use_lt, bool):
            return False, "use_latent_typicality deve ser booleano"
        if use_lt and not representations_matrix_available(DEFAULT_REPRESENTATIONS_MATRIX):
            return False, "Matriz de representacoes nao encontrada; execute extract_synthetic_image_representations_optimized.py primeiro."
        lt_system = parameters.get("typicality_system")
        if lt_system is not None and str(lt_system).upper() not in _TYPICALITY_SYSTEMS:
            return False, f"typicality_system deve ser um de: {', '.join(_TYPICALITY_SYSTEMS)}"
        lt_k = parameters.get("typicality_k")
        if lt_k is not None:
            try:
                if int(lt_k) < 1:
                    raise ValueError
            except (TypeError, ValueError):
                return False, "typicality_k deve ser um inteiro positivo"
        lt_distance = parameters.get("typicality_distance")
        if lt_distance is not None and str(lt_distance).lower() not in _TYPICALITY_DISTANCES:
            return False, f"typicality_distance deve ser um de: {', '.join(_TYPICALITY_DISTANCES)}"
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
            selected_analyses = parameters.get("selected_analyses")
            use_latent_typicality = bool(parameters.get("use_latent_typicality", False))

            analysis = run_synthetic_image_detection_analysis(
                image,
                generate_visuals=generate_visuals,
                selected_analyses=selected_analyses,
                on_progress=on_progress,
                return_embedding=use_latent_typicality,
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
                "selected_analyses": analysis.get("selected_analyses", selected_analyses),
                "inference_device": analysis.get("inference_device", "cpu"),
                "individual_results": analysis["individual_results"],
                "detector_scores": _detector_scores_for_json(analysis.get("detector_scores", {})),
                "model_scores_txt_path": str(scores_path),
                "model_scores_filename": "model_scores.txt",
                "input_image_path": save_pil(analysis.get("input_image"), "input_image"),
                "input_fft_image_path": save_pil(analysis.get("input_fft"), "input_fft"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            if bool(parameters.get("reference_lr_enabled", False)):
                report_progress(on_progress, 96, "Calibrando LR com populacao de referencia…")
                try:
                    use_augmented = bool(parameters.get("use_augmented_reference"))
                    rep_available = representations_matrix_available(DEFAULT_REPRESENTATIONS_MATRIX)
                    if use_latent_typicality or (use_augmented and rep_available):
                        score_matrix = DEFAULT_REPRESENTATIONS_MATRIX
                    elif use_augmented:
                        score_matrix = _AUGMENTED_SCORE_MATRIX
                    else:
                        score_matrix = DEFAULT_SCORE_MATRIX
                    sample_multiplier = AUGMENTATION_MULTIPLIER if use_augmented else 1
                    lr_report = compute_reference_lr(
                        detector_scores=analysis.get("detector_scores", {}),
                        selection=parameters.get("reference_population"),
                        out_dir=out_dir,
                        score_matrix=score_matrix,
                        selected_detectors=tuple(
                            selected_analyses
                            or (
                                "ai_image_detector_deploy",
                                "sdxl_flux_detector_v1_1",
                                "bfree",
                                "corvi2023",
                                "safe",
                            )
                        ),
                        classifier=str(parameters.get("meta_classifier", "logistic")).lower().strip(),
                        sample_multiplier=sample_multiplier,
                        use_latent_typicality=use_latent_typicality,
                        typicality_system=str(parameters.get("typicality_system", DEFAULT_TYPICALITY_SYSTEM)),
                        typicality_k=int(parameters.get("typicality_k", DEFAULT_TYPICALITY_K)),
                        typicality_distance=str(parameters.get("typicality_distance", DEFAULT_TYPICALITY_DISTANCE)),
                    )
                    result["reference_lr"] = lr_report
                    result["reference_lr_report_filename"] = "lr_reference_report.json"
                    result["reference_lr_summary_filename"] = lr_report["artifact_filenames"]["summary"]
                    result["reference_lr_tippett_filename"] = lr_report["artifact_filenames"]["tippett"]
                    result["reference_lr_distribution_filename"] = lr_report["artifact_filenames"]["distribution"]
                    result["reference_lr_identity_filename"] = lr_report["artifact_filenames"]["identity"]
                except Exception as exc:
                    result["reference_lr"] = {
                        "success": False,
                        "error": str(exc),
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
