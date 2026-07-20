"""RetinaFace crop alinhado para entrada MoE-FFD (reusa detector do PAD)."""

from __future__ import annotations

import math
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

from core.legacy.pad.runtime import pad_models_dir

_detector_lock = threading.Lock()
_detector_net = None
_detector_dir: Optional[str] = None


def retinaface_detection_dir() -> Path:
    return (pad_models_dir() / "detection_model").resolve()


def retinaface_available() -> Tuple[bool, str]:
    detection = retinaface_detection_dir()
    deploy = detection / "deploy.prototxt"
    caffemodel = detection / "Widerface-RetinaFace.caffemodel"
    if not deploy.is_file() or not caffemodel.is_file():
        return False, f"RetinaFace ausente em {detection} (necessario para crop facial MoE-FFD)"
    return True, ""


def _get_detector():
    global _detector_net, _detector_dir
    ok, reason = retinaface_available()
    if not ok:
        raise RuntimeError(reason)
    detection = str(retinaface_detection_dir())
    with _detector_lock:
        if _detector_net is None or _detector_dir != detection:
            deploy = str(Path(detection) / "deploy.prototxt")
            caffemodel = str(Path(detection) / "Widerface-RetinaFace.caffemodel")
            _detector_net = cv2.dnn.readNetFromCaffe(deploy, caffemodel)
            _detector_dir = detection
        return _detector_net


def detect_main_face_bbox(
    rgb: np.ndarray,
    *,
    confidence_threshold: float = 0.6,
) -> Tuple[Optional[list[int]], float]:
    """Detect highest-confidence face. Bbox = [x, y, w, h] in original coords.

    Uses the same WiderFace-RetinaFace Caffe net as PAD (expects BGR for blob).
    """
    image = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    height, width = image.shape[:2]
    aspect_ratio = width / height if height > 0 else 1.0
    resized = image
    if width * height >= 192 * 192:
        resized = cv2.resize(
            image,
            (int(192 * math.sqrt(aspect_ratio)), int(192 / math.sqrt(aspect_ratio))),
            interpolation=cv2.INTER_LINEAR,
        )

    detector = _get_detector()
    blob = cv2.dnn.blobFromImage(resized, 1, mean=(104, 117, 123))
    detector.setInput(blob, "data")
    out = detector.forward("detection_out").squeeze()
    if out.ndim == 1:
        out = out.reshape(1, -1)
    if out.size == 0 or out.shape[0] == 0:
        return None, 0.0

    max_conf_index = int(np.argmax(out[:, 2]))
    conf = float(out[max_conf_index, 2])
    if conf < confidence_threshold:
        return None, conf

    left = int(out[max_conf_index, 3] * width)
    top = int(out[max_conf_index, 4] * height)
    right = int(out[max_conf_index, 5] * width)
    bottom = int(out[max_conf_index, 6] * height)
    bbox = [left, top, max(1, right - left + 1), max(1, bottom - top + 1)]
    return bbox, conf


def crop_aligned_face(
    rgb: np.ndarray,
    *,
    margin: float = 1.3,
    confidence_threshold: float = 0.6,
) -> Dict[str, Any]:
    """Crop square face region with margin (FF++-style aligned input).

    Returns:
      face_rgb, detector_bbox, crop_bbox, face_confidence, margin, cropped
    """
    if margin < 1.0:
        raise ValueError("face_margin deve ser >= 1.0")

    bbox, conf = detect_main_face_bbox(rgb, confidence_threshold=confidence_threshold)
    if bbox is None or bbox[2] <= 0 or bbox[3] <= 0:
        raise RuntimeError(
            f"NO_FACE_DETECTED: nenhuma face RetinaFace acima do limiar "
            f"{confidence_threshold:.2f} (conf={conf:.3f})"
        )

    x, y, w, h = bbox
    cx = x + w / 2.0
    cy = y + h / 2.0
    side = max(w, h) * float(margin)
    half = side / 2.0

    img_h, img_w = rgb.shape[:2]
    x0 = int(round(cx - half))
    y0 = int(round(cy - half))
    x1 = int(round(cx + half))
    y1 = int(round(cy + half))

    pad_l = max(0, -x0)
    pad_t = max(0, -y0)
    pad_r = max(0, x1 - img_w)
    pad_b = max(0, y1 - img_h)
    work = rgb
    if pad_l or pad_t or pad_r or pad_b:
        work = cv2.copyMakeBorder(rgb, pad_t, pad_b, pad_l, pad_r, cv2.BORDER_REPLICATE)
        x0 += pad_l
        y0 += pad_t
        x1 += pad_l
        y1 += pad_t

    face = work[y0:y1, x0:x1]
    if face.size == 0:
        raise RuntimeError("NO_FACE_DETECTED: crop facial vazio apos clamp")

    fh, fw = face.shape[:2]
    side_i = min(fh, fw)
    face = np.ascontiguousarray(face[:side_i, :side_i])

    return {
        "face_rgb": face,
        "detector_bbox": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
        "crop_bbox": {
            "x": int(round(cx - half)),
            "y": int(round(cy - half)),
            "w": int(side_i),
            "h": int(side_i),
        },
        "face_confidence": float(conf),
        "margin": float(margin),
        "cropped": True,
    }
