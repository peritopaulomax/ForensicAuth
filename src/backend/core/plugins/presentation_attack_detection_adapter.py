"""Adapter — detecção de ataques de apresentação facial (PAD)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import cv2
import numpy as np
import torch

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.pad.anti_spoof_predict import AntiSpoofPredict
from core.legacy.pad.generate_patches import CropImage
from core.legacy.pad.runtime import pad_models_dir, pad_runtime_status
from core.legacy.pad.utility import parse_model_name
from core.progress import pop_progress_callback, report_progress
from core.technique_ids import PRESENTATION_ATTACK_DETECTION

_PAD_DEFAULT_THRESHOLD = float(os.environ.get("PAD_DEFAULT_THRESHOLD", "0.5"))


def _pad_anti_spoof_models_dir() -> Path:
    return pad_models_dir() / "anti_spoof_models"


def _pad_detection_model_dir() -> Path:
    return pad_models_dir() / "detection_model"


def _get_main_face_bbox(detector, image: np.ndarray, confidence_threshold: float = 0.6):
    """Detect the highest-confidence face and return its bbox + confidence.

    Mirrors the preprocessing in the vendored ``Detection.get_bbox`` but also
    surfaces the confidence score so the adapter can reject low-confidence
    detections.
    """
    height, width = image.shape[:2]
    aspect_ratio = width / height if height > 0 else 1.0
    resized = image
    if width * height >= 192 * 192:
        resized = cv2.resize(
            image,
            (int(192 * np.sqrt(aspect_ratio)), int(192 / np.sqrt(aspect_ratio))),
            interpolation=cv2.INTER_LINEAR,
        )

    blob = cv2.dnn.blobFromImage(resized, 1, mean=(104, 117, 123))
    detector.setInput(blob, "data")
    out = detector.forward("detection_out").squeeze()
    if out.ndim == 1:
        out = out.reshape(1, -1)

    max_conf_index = int(np.argmax(out[:, 2]))
    conf = float(out[max_conf_index, 2])
    if conf < confidence_threshold:
        return None, conf

    left = int(out[max_conf_index, 3] * width)
    top = int(out[max_conf_index, 4] * height)
    right = int(out[max_conf_index, 5] * width)
    bottom = int(out[max_conf_index, 6] * height)
    bbox = [left, top, right - left + 1, bottom - top + 1]
    return bbox, conf


class PresentationAttackDetectionAdapter(ForensicPlugin):
    """Detecção de ataques de apresentação facial via MiniFASNet + RetinaFace."""

    @property
    def name(self) -> str:
        return PRESENTATION_ATTACK_DETECTION

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    @classmethod
    def is_runtime_available(cls) -> Tuple[bool, str]:
        return pad_runtime_status()

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        ok, reason = pad_runtime_status()
        if not ok:
            return False, reason

        threshold = parameters.get("threshold", _PAD_DEFAULT_THRESHOLD)
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            return False, "threshold deve ser um numero entre 0 e 1"
        if not 0.0 <= threshold <= 1.0:
            return False, "threshold deve estar entre 0 e 1"

        device_id = parameters.get("device_id", 0)
        try:
            int(device_id)
        except (TypeError, ValueError):
            return False, "device_id deve ser um inteiro"

        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        ok, reason = pad_runtime_status()
        if not ok:
            return {
                "success": False,
                "error": reason,
                "adapter": PRESENTATION_ATTACK_DETECTION,
                "status": "unavailable",
            }

        try:
            report_progress(on_progress, 5, "Carregando modelo de deteccao facial")
            device_id = int(parameters.get("device_id", 0))
            model_dir = _pad_anti_spoof_models_dir()
            detection_model_dir = _pad_detection_model_dir()

            image = cv2.imread(evidence_path)
            if image is None:
                return {
                    "success": False,
                    "error": "FAILED_TO_LOAD_IMAGE",
                    "message": "Nao foi possivel carregar a imagem de evidencia.",
                    "adapter": PRESENTATION_ATTACK_DETECTION,
                }

            height, width = image.shape[:2]

            report_progress(on_progress, 15, "Detectando face principal")
            model_test = AntiSpoofPredict(device_id, str(detection_model_dir))

            image_bbox, face_conf = _get_main_face_bbox(model_test.detector, image)
            if image_bbox is None or image_bbox[2] <= 0 or image_bbox[3] <= 0:
                return {
                    "success": False,
                    "error": "NO_FACE_DETECTED",
                    "message": "Nenhuma face detectada na imagem.",
                    "adapter": PRESENTATION_ATTACK_DETECTION,
                }

            report_progress(on_progress, 35, "Classificando com MiniFASNet")
            image_cropper = CropImage()
            prediction = np.zeros((1, 3))
            model_names = sorted([p.name for p in model_dir.glob("*.pth")])

            if not model_names:
                return {
                    "success": False,
                    "error": "NO_MODELS_FOUND",
                    "message": f"Nenhum modelo PAD encontrado em {model_dir}",
                    "adapter": PRESENTATION_ATTACK_DETECTION,
                }

            inference_device = "cpu"
            for model_name in model_names:
                h_input, w_input, model_type, scale = parse_model_name(model_name)
                param = {
                    "org_img": image,
                    "bbox": image_bbox,
                    "scale": scale,
                    "out_w": w_input,
                    "out_h": h_input,
                    "crop": scale is not None,
                }
                img = image_cropper.crop(**param)
                prediction += model_test.predict(img, str(model_dir / model_name))
                if model_test.device.type != "cpu":
                    inference_device = "cuda"

            label = int(np.argmax(prediction))
            raw_value = float(prediction[0][label] / 2)
            threshold = float(parameters.get("threshold", _PAD_DEFAULT_THRESHOLD))

            # Original mapping: label 1 == real; others == fake.
            raw_label = "real" if label == 1 else "fake"

            # Convert the model's confidence into a "probability of being real" so
            # that the configurable threshold (PAD-RN-03) behaves intuitively.
            # The raw score is preserved for forensic traceability.
            score = raw_value if raw_label == "real" else 1.0 - raw_value
            final_label = "real" if score > threshold else "fake"

            report_progress(on_progress, 80, "Gerando visualizacoes")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            out_dir = job_artifact_dir(parameters, fallback_subdir="pad_tmp")
            out_dir.mkdir(parents=True, exist_ok=True)

            x, y, w, h = image_bbox
            color = (0, 0, 255) if final_label == "fake" else (255, 0, 0)
            annotated = image.copy()
            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
            result_text = f"{'Fake' if final_label == 'fake' else 'Real'} Face Score: {score:.2f}"
            cv2.putText(
                annotated,
                result_text,
                (x, y - 5),
                cv2.FONT_HERSHEY_COMPLEX,
                0.5 * image.shape[0] / 1024,
                color,
            )

            annotated_path = out_dir / f"pad_annotated_{stamp}.png"
            cv2.imwrite(str(annotated_path), annotated)

            face_crop = image[y : y + h, x : x + w]
            face_crop_path = out_dir / f"pad_face_crop_{stamp}.png"
            cv2.imwrite(str(face_crop_path), face_crop)

            result_json = {
                "label": final_label,
                "raw_label": raw_label,
                "score": round(score, 6),
                "raw_score": round(raw_value, 6),
                "threshold": threshold,
                "bbox": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
                "inference_device": inference_device,
                "models_used": model_names,
                "image_width": int(width),
                "image_height": int(height),
            }
            result_json_path = out_dir / f"pad_result_{stamp}.json"
            result_json_path.write_text(json.dumps(result_json, indent=2), encoding="utf-8")

            report_progress(on_progress, 100, "Concluido")

            return {
                "success": True,
                "adapter": PRESENTATION_ATTACK_DETECTION,
                "status": "completed",
                "label": final_label,
                "raw_label": raw_label,
                "score": score,
                "threshold": threshold,
                "bbox": result_json["bbox"],
                "inference_device": inference_device,
                "models_used": model_names,
                "pad_result_json_path": str(result_json_path),
                "pad_result_filename": "pad_result.json",
                "pad_face_crop_path": str(face_crop_path),
                "pad_face_crop_filename": "pad_face_crop.png",
                "pad_annotated_image_path": str(annotated_path),
                "pad_annotated_image_filename": "pad_annotated.png",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as exc:
            return {
                "success": False,
                "error": "ADAPTER_ERROR",
                "message": str(exc),
                "adapter": PRESENTATION_ATTACK_DETECTION,
            }
