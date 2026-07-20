"""Adapter — MoE-FFD face forgery detection (deepfake / face manipulation)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import cv2

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.moe_ffd.runtime import moe_ffd_runtime_status
from core.progress import pop_progress_callback, report_progress
from core.technique_ids import MOE_FFD

_MOE_FFD_DEFAULT_THRESHOLD = float(os.environ.get("MOE_FFD_DEFAULT_THRESHOLD", "0.5"))
_MOE_FFD_FACE_MARGIN = float(os.environ.get("MOE_FFD_FACE_MARGIN", "1.3"))
_MOE_FFD_FACE_CONF = float(os.environ.get("MOE_FFD_FACE_CONF", "0.6"))


class MoeFfdAdapter(ForensicPlugin):
    """Face forgery detection via official MoE-FFD ViT-MoE checkpoint."""

    @property
    def name(self) -> str:
        return MOE_FFD

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    @classmethod
    def is_runtime_available(cls) -> Tuple[bool, str]:
        return moe_ffd_runtime_status()

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        ok, reason = moe_ffd_runtime_status()
        if not ok:
            return False, reason

        threshold = parameters.get("threshold", _MOE_FFD_DEFAULT_THRESHOLD)
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            return False, "threshold deve ser um numero entre 0 e 1"
        if not 0.0 <= threshold <= 1.0:
            return False, "threshold deve estar entre 0 e 1"

        margin = parameters.get("face_margin", _MOE_FFD_FACE_MARGIN)
        try:
            margin = float(margin)
        except (TypeError, ValueError):
            return False, "face_margin deve ser um numero >= 1.0"
        if margin < 1.0:
            return False, "face_margin deve ser >= 1.0"

        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        ok, reason = moe_ffd_runtime_status()
        if not ok:
            return {
                "success": False,
                "error": reason,
                "adapter": MOE_FFD,
                "status": "unavailable",
            }

        threshold = float(parameters.get("threshold", _MOE_FFD_DEFAULT_THRESHOLD))
        prefer_cuda = bool(parameters.get("prefer_cuda", True))
        crop_face = bool(parameters.get("crop_face", True))
        face_margin = float(parameters.get("face_margin", _MOE_FFD_FACE_MARGIN))
        face_confidence = float(parameters.get("face_confidence", _MOE_FFD_FACE_CONF))

        try:
            report_progress(on_progress, 5, "Preparando runtime MoE-FFD")
            from core.legacy.moe_ffd import moe_ffd_pipeline as pipeline

            report_progress(on_progress, 15, "Detectando e recortando face (RetinaFace)")
            report_progress(on_progress, 35, f"Inferencia MoE-FFD ({'GPU' if prefer_cuda else 'CPU'})")
            inference = pipeline.infer(
                evidence_path,
                threshold=threshold,
                prefer_cuda=prefer_cuda,
                crop_face=crop_face,
                face_margin=face_margin,
                face_confidence=face_confidence,
            )

            report_progress(on_progress, 80, "Gerando artefatos")
            out_dir = job_artifact_dir(parameters, fallback_subdir="moe_ffd_tmp")
            out_dir.mkdir(parents=True, exist_ok=True)

            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            face_rgb = inference.pop("face_rgb", None)

            result_payload = {
                "label": inference["label"],
                "fake_prob": inference["fake_prob"],
                "real_prob": inference["real_prob"],
                "score": inference["score"],
                "threshold": inference["threshold"],
                "inference_device": inference["inference_device"],
                "model_checkpoint": inference["model_checkpoint"],
                "checkpoint_epoch": inference.get("checkpoint_epoch"),
                "preprocess": inference.get("preprocess"),
                "class_mapping": inference.get("class_mapping"),
                "face_cropped": inference.get("face_cropped"),
                "face_confidence": inference.get("face_confidence"),
                "face_margin": inference.get("face_margin"),
                "detector_bbox": inference.get("detector_bbox"),
                "crop_bbox": inference.get("crop_bbox"),
                "original_shape": inference.get("original_shape"),
                "input_tensor_shape": inference.get("input_tensor_shape"),
                "input_tensor_mean": inference.get("input_tensor_mean"),
                "logits": inference.get("logits"),
                "timestamp": stamp,
                "evidence_path": str(evidence_path),
            }

            result_json = out_dir / "moe_ffd_result.json"
            summary_txt = out_dir / "moe_ffd_summary.txt"
            face_crop_path = out_dir / "moe_ffd_face_crop.png"
            input_copy = out_dir / "moe_ffd_input.png"

            result_json.write_text(json.dumps(result_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            summary_txt.write_text(
                (
                    f"MoE-FFD Face Forgery Detection\n"
                    f"label={inference['label']}\n"
                    f"fake_prob={inference['fake_prob']:.6f}\n"
                    f"real_prob={inference['real_prob']:.6f}\n"
                    f"threshold={inference['threshold']:.4f}\n"
                    f"device={inference['inference_device']}\n"
                    f"checkpoint={inference['model_checkpoint']}\n"
                    f"face_cropped={inference.get('face_cropped')}\n"
                    f"face_confidence={inference.get('face_confidence')}\n"
                    f"face_margin={inference.get('face_margin')}\n"
                    f"preprocess={inference.get('preprocess')}\n"
                ),
                encoding="utf-8",
            )

            if face_rgb is not None:
                bgr = cv2.cvtColor(face_rgb, cv2.COLOR_RGB2BGR)
                cv2.imwrite(str(face_crop_path), bgr)
                cv2.imwrite(str(input_copy), bgr)
            else:
                face_crop_path = Path(evidence_path)
                input_copy = Path(evidence_path)

            report_progress(on_progress, 100, "MoE-FFD concluido")
            return {
                "success": True,
                "adapter": MOE_FFD,
                "status": "completed",
                "label": inference["label"],
                "fake_prob": inference["fake_prob"],
                "real_prob": inference["real_prob"],
                "score": inference["score"],
                "threshold": inference["threshold"],
                "inference_device": inference["inference_device"],
                "model_checkpoint": inference["model_checkpoint"],
                "face_cropped": inference.get("face_cropped"),
                "face_confidence": inference.get("face_confidence"),
                "detector_bbox": inference.get("detector_bbox"),
                "crop_bbox": inference.get("crop_bbox"),
                "moe_ffd_result_json_path": str(result_json),
                "moe_ffd_summary_txt_path": str(summary_txt),
                "moe_ffd_face_crop_path": str(face_crop_path),
                "input_image_path": str(input_copy),
            }
        except Exception as exc:
            err = str(exc)
            status = "failed"
            if "NO_FACE_DETECTED" in err:
                status = "no_face"
            return {
                "success": False,
                "error": err,
                "adapter": MOE_FFD,
                "status": status,
            }
