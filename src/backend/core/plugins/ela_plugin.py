"""Error Level Analysis (ELA) plugin for image forensics.

Re-saves the image at a known quality level and computes the difference
between the original and the re-saved version. Areas with high difference
(indicating they were not saved at the target quality) are highlighted.

Channel modes:
- rgb: full-color difference (default)
- y: luminance (Y) only
- crominancia: mono (Cb+Cr)/2 vs ELA on chrominance average
- r/g/b: single BGR channel vs ELA on that channel
"""

from pathlib import Path
from typing import Any, Dict, Tuple

import cv2
import numpy as np

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.progress import pop_progress_callback, report_progress

CHANNEL_MODES = ("rgb", "y", "crominancia", "r", "g", "b")
BASE_ELA_SCALE = 15


class ELAPlugin(ForensicPlugin):
    """Error Level Analysis forensic plugin."""

    @property
    def name(self) -> str:
        return "ela"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        quality = parameters.get("quality", 95)
        if not isinstance(quality, (int, float)) or not (50 <= quality <= 100):
            return False, "Quality must be between 50 and 100"

        gain = parameters.get("gain", 1.0)
        if not isinstance(gain, (int, float)) or not (0.1 <= gain <= 10):
            return False, "Gain must be between 0.1 and 10"

        discard_v = parameters.get("discard_vertical", 0)
        discard_h = parameters.get("discard_horizontal", 0)
        if not isinstance(discard_v, int) or not (0 <= discard_v <= 7):
            return False, "discard_vertical must be an integer between 0 and 7"
        if not isinstance(discard_h, int) or not (0 <= discard_h <= 7):
            return False, "discard_horizontal must be an integer between 0 and 7"

        channel_mode = parameters.get("channel_mode", "rgb")
        if channel_mode not in CHANNEL_MODES:
            return False, f"channel_mode must be one of: {', '.join(CHANNEL_MODES)}"

        return True, ""

    @staticmethod
    def _chrominance_avg(image_bgr: np.ndarray) -> np.ndarray:
        """Monochromatic chrominance: (Cb + Cr) / 2 from YCrCb decomposition."""
        ycrcb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2YCrCb)
        cb = ycrcb[:, :, 1].astype(np.float32)
        cr = ycrcb[:, :, 2].astype(np.float32)
        return np.clip((cb + cr) / 2.0, 0, 255).astype(np.uint8)

    @staticmethod
    def _extract_channel(image_bgr: np.ndarray, channel_mode: str) -> np.ndarray:
        if channel_mode == "y":
            return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2YCrCb)[:, :, 0]
        if channel_mode == "crominancia":
            return ELAPlugin._chrominance_avg(image_bgr)
        if channel_mode == "r":
            return image_bgr[:, :, 2]
        if channel_mode == "g":
            return image_bgr[:, :, 1]
        if channel_mode == "b":
            return image_bgr[:, :, 0]
        raise ValueError(f"Unsupported channel mode: {channel_mode}")

    @staticmethod
    def _single_to_bgr(channel: np.ndarray) -> np.ndarray:
        return cv2.cvtColor(channel, cv2.COLOR_GRAY2BGR)

    @staticmethod
    def _scale_diff(diff: np.ndarray, gain: float) -> np.ndarray:
        return np.clip(diff.astype(np.float32) * gain * BASE_ELA_SCALE, 0, 255).astype(np.uint8)

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        ext = Path(evidence_path).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"):
            return {"success": False, "error": "ELA requires an image file"}

        quality = int(parameters.get("quality", 95))
        gain = float(parameters.get("gain", 1.0))
        discard_v = int(parameters.get("discard_vertical", 0))
        discard_h = int(parameters.get("discard_horizontal", 0))
        channel_mode = parameters.get("channel_mode", "rgb")
        on_progress = pop_progress_callback(parameters)

        result_dir = job_artifact_dir(parameters, fallback_subdir="ela")

        report_progress(on_progress, 8, "Carregando imagem")
        original = cv2.imread(evidence_path)
        if original is None:
            return {"success": False, "error": "Could not read image"}

        h, w = original.shape[:2]

        if discard_v > 0 or discard_h > 0:
            top = min(discard_v, h // 2)
            bottom = max(h - discard_v if discard_v > 0 else h, h // 2 + 1)
            left = min(discard_h, w // 2)
            right = max(w - discard_h if discard_h > 0 else w, w // 2 + 1)
            original = original[top:bottom, left:right]
            h, w = original.shape[:2]

        report_progress(on_progress, 35, "Recompactando JPEG para ELA")
        ok, encoded = cv2.imencode(".jpg", original, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            return {"success": False, "error": "Failed to re-encode image as JPEG for ELA"}
        resaved = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if resaved is None:
            return {"success": False, "error": "Failed to decode re-saved JPEG for ELA"}

        report_progress(on_progress, 62, f"Calculando diferenca ELA ({channel_mode})")
        if channel_mode == "rgb":
            diff = cv2.absdiff(original, resaved)
            diff_scaled = self._scale_diff(diff, gain)
            display_original = original
            ela_score = float(np.mean(diff))
        else:
            ch_orig = self._extract_channel(original, channel_mode)
            ch_resaved = self._extract_channel(resaved, channel_mode)
            diff = cv2.absdiff(ch_orig, ch_resaved)
            diff_scaled = self._scale_diff(diff, gain)
            display_original = self._single_to_bgr(ch_orig)
            diff_scaled = self._single_to_bgr(diff_scaled)
            ela_score = float(np.mean(diff))

        base_name = Path(evidence_path).stem
        heatmap_path = result_dir / f"{base_name}_ela_heatmap.png"
        original_crop_path = result_dir / f"{base_name}_ela_original.png"
        report_progress(on_progress, 88, "Salvando heatmap e original recortado")
        heatmap_base = self._scale_diff(diff, 1.0)
        if channel_mode != "rgb":
            heatmap_base = self._single_to_bgr(heatmap_base)
        heatmap_base_path = result_dir / f"{base_name}_ela_heatmap_base.png"
        cv2.imwrite(str(heatmap_base_path), heatmap_base)
        cv2.imwrite(str(heatmap_path), diff_scaled)
        cv2.imwrite(str(original_crop_path), display_original)

        return {
            "success": True,
            "ela_score": round(ela_score, 4),
            "heatmap_path": str(heatmap_path),
            "heatmap_base_path": str(heatmap_base_path),
            "original_crop_path": str(original_crop_path),
            "quality": quality,
            "gain": gain,
            "discard_vertical": discard_v,
            "discard_horizontal": discard_h,
            "channel_mode": channel_mode,
            "dimensions": {"height": h, "width": w},
        }
