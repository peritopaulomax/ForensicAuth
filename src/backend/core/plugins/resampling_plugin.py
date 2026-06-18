"""Deteccao de reamostragem (Mahdian & Saic 2008).

Derivada de 2a ordem, Radon theta=0, espectro de covariancia FFT.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.fftpack import fft
from scipy.signal import correlate

from app.config import get_settings
from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.progress import pop_progress_callback, report_progress

ORDER = 2  # derivada de 2a ordem (especificacao Mahdian & Saic)


def _radon_theta_zero(image: np.ndarray) -> np.ndarray:
    return np.sum(np.abs(image), axis=1, keepdims=True)


def _covariance_spectrum_full(projection: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """FFT completo da autocovariancia (ambos os lados, nao so ate Nyquist)."""
    r = np.diff(projection, axis=0)
    ft = np.abs(fft(correlate(r[:, 0], r[:, 0], mode="full")))
    for i in range(1, r.shape[1]):
        ft = np.maximum(ft, np.abs(fft(correlate(r[:, i], r[:, i], mode="full"))))
    ft = ft / (np.linalg.norm(ft) + 1e-12)
    ll = len(ft)
    # Eixo 0..2 (espectro completo, simetrico em torno de Nyquist em 1.0)
    freqs = (np.arange(1, ll + 1, dtype=float)) / (ll / 2.0)
    return freqs, ft


def _clamp_polygon(polygon: List[List[int]], w_img: int, h_img: int) -> List[List[int]]:
    return [
        [max(0, min(w_img - 1, int(p[0]))), max(0, min(h_img - 1, int(p[1])))]
        for p in polygon
    ]


def _apply_polygon_roi(
    channel: np.ndarray,
    polygon: Optional[List[List[int]]],
    *,
    complement: bool = False,
) -> Tuple[np.ndarray, Optional[Dict[str, Any]]]:
    if not polygon or len(polygon) < 3:
        return channel, None

    h_img, w_img = channel.shape[:2]
    polygon = _clamp_polygon(polygon, w_img, h_img)
    contour = np.array(polygon, dtype=np.int32).reshape(-1, 1, 2)
    peri = cv2.arcLength(contour, True)
    if peri > 0:
        epsilon = max(1.0, 0.002 * peri)
        contour = cv2.approxPolyDP(contour, epsilon, True)
    if len(contour) < 3:
        return channel, None

    if complement:
        work = channel.astype(float).copy()
        full_mask = np.zeros((h_img, w_img), dtype=np.uint8)
        cv2.fillPoly(full_mask, [contour], 255)
        work[full_mask > 0] = 0.0
        return work, {"complement": True, "polygon": contour.reshape(-1, 2).tolist()}

    x, y, w, h = cv2.boundingRect(contour)
    if w < 4 or h < 4:
        return channel, None

    x = max(0, min(x, w_img - 1))
    y = max(0, min(y, h_img - 1))
    w = min(w, w_img - x)
    h = min(h, h_img - y)

    crop = channel[y : y + h, x : x + w].astype(float).copy()
    mask = np.zeros((h, w), dtype=np.uint8)
    pts_rel = contour.reshape(-1, 2) - np.array([x, y], dtype=np.int32)
    cv2.fillPoly(mask, [pts_rel.reshape(-1, 1, 2)], 255)
    crop[mask == 0] = 0.0
    polygon_used = contour.reshape(-1, 2).tolist()

    return crop, {"x": int(x), "y": int(y), "w": int(w), "h": int(h), "polygon": polygon_used}


def _normalize_u8(arr: np.ndarray) -> np.ndarray:
    arr = arr.astype(float)
    mn, mx = float(np.min(arr)), float(np.max(arr))
    span = mx - mn or 1.0
    return ((arr - mn) / span * 255).astype(np.uint8)


def _save_spectrum_plot(path: Path, freqs: np.ndarray, spec: np.ndarray, direction: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(freqs, spec, color="#dc2626", linewidth=0.8)
    ax.set_title(f"FFT da Covariancia ({direction}) — espectro completo")
    ax.set_xlabel("Frequencia normalizada")
    ax.set_ylabel("Magnitude normalizada")
    for x in np.arange(0, 1.125, 0.125):
        ax.axvline(x, color="#94a3b8", linestyle="--", alpha=0.6, linewidth=0.8)
    for x in np.arange(1.0, 2.125, 0.125):
        ax.axvline(x, color="#94a3b8", linestyle="--", alpha=0.6, linewidth=0.8)
    fig.tight_layout()
    fig.savefig(str(path), dpi=120)
    plt.close(fig)


def _save_combined_spectrum(path: Path, fv: np.ndarray, sv: np.ndarray, fh: np.ndarray, sh: np.ndarray) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 4))
    axes[0].plot(fv, sv, color="#dc2626", linewidth=0.8)
    axes[0].set_title("FFT vertical (completo)")
    axes[1].plot(fh, sh, color="#dc2626", linewidth=0.8)
    axes[1].set_title("FFT horizontal (completo)")
    for ax in axes:
        ax.set_xlabel("Frequencia normalizada")
        for x in list(np.arange(0, 1.125, 0.125)) + list(np.arange(1.0, 2.125, 0.125)):
            ax.axvline(x, color="#94a3b8", linestyle="--", alpha=0.5, linewidth=0.7)
    fig.tight_layout()
    fig.savefig(str(path), dpi=120)
    plt.close(fig)


class ResamplingPlugin(ForensicPlugin):
    """Detect resampling periodicity in images."""

    @property
    def name(self) -> str:
        return "resampling"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        mode = parameters.get("channel_mode", "luminance")
        if mode not in ("luminance", "r", "g", "b", "consolidated"):
            return False, "channel_mode invalido"
        poly = parameters.get("polygon")
        if poly is not None and not isinstance(poly, list):
            return False, "polygon deve ser lista de pontos [x,y]"
        return True, ""

    def _load_bgr(self, evidence_path: str) -> np.ndarray:
        """Carrega BGR com orientacao EXIF (mesma exibicao do navegador)."""
        from PIL import Image, ImageOps

        try:
            pil = Image.open(evidence_path)
            pil = ImageOps.exif_transpose(pil)
            if pil.mode in ("RGBA", "LA"):
                pil = pil.convert("RGB")
            elif pil.mode != "RGB":
                pil = pil.convert("RGB")
            rgb = np.asarray(pil)
            if rgb.ndim == 2:
                return cv2.cvtColor(rgb, cv2.COLOR_GRAY2BGR)
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        except Exception:
            image = cv2.imread(evidence_path, cv2.IMREAD_COLOR)
            if image is None:
                gray = cv2.imread(evidence_path, cv2.IMREAD_GRAYSCALE)
                if gray is None:
                    raise ValueError("Falha ao carregar imagem")
                return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            return image

    def _channel_from_bgr(self, bgr: np.ndarray, mode: str) -> np.ndarray:
        if bgr.ndim == 2 or bgr.shape[2] == 1:
            return bgr.astype(float)
        if mode == "luminance":
            return cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(float)
        if mode == "r":
            return bgr[:, :, 2].astype(float)
        if mode == "g":
            return bgr[:, :, 1].astype(float)
        if mode == "b":
            return bgr[:, :, 0].astype(float)
        raise ValueError(f"channel_mode desconhecido: {mode}")

    def _process_channel(
        self,
        channel: np.ndarray,
        polygon: Optional[List[List[int]]],
        *,
        polygon_complement: bool = False,
    ) -> Dict[str, Any]:
        roi, roi_meta = _apply_polygon_roi(channel, polygon, complement=polygon_complement)
        d_v = np.diff(roi, n=ORDER, axis=0)
        d_h = np.diff(roi, n=ORDER, axis=1)
        r_v = _radon_theta_zero(np.abs(d_v))
        r_h = _radon_theta_zero(np.abs(d_h))
        freqs_v, spec_v = _covariance_spectrum_full(r_v)
        freqs_h, spec_h = _covariance_spectrum_full(r_h)
        return {
            "roi": roi,
            "roi_meta": roi_meta,
            "deriv_v": d_v,
            "deriv_h": d_h,
            "freqs_v": freqs_v,
            "spec_v": spec_v,
            "freqs_h": freqs_h,
            "spec_h": spec_h,
        }

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        try:
            report_progress(on_progress, 10, "Carregando imagem")
            bgr = self._load_bgr(evidence_path)
            is_color = bgr.ndim == 3 and bgr.shape[2] >= 3
            channel_mode = str(parameters.get("channel_mode", "luminance"))
            if not is_color:
                channel_mode = "luminance"

            polygon = parameters.get("polygon")
            if polygon:
                polygon = [[int(p[0]), int(p[1])] for p in polygon]
            polygon_complement = bool(parameters.get("polygon_complement", False))

            if channel_mode == "consolidated" and is_color:
                channels = ["r", "g", "b"]
                results = []
                for i, ch in enumerate(channels):
                    report_progress(on_progress, 20 + i * 18, f"Canal {ch.upper()}")
                    results.append(
                        self._process_channel(
                            self._channel_from_bgr(bgr, ch),
                            polygon,
                            polygon_complement=polygon_complement,
                        )
                    )
                spec_v = np.mean([r["spec_v"] for r in results], axis=0)
                spec_h = np.mean([r["spec_h"] for r in results], axis=0)
                freqs_v = results[0]["freqs_v"]
                freqs_h = results[0]["freqs_h"]
                deriv_v = np.mean([np.abs(r["deriv_v"]) for r in results], axis=0)
                deriv_h = np.mean([np.abs(r["deriv_h"]) for r in results], axis=0)
                roi = results[0]["roi"]
                roi_meta = results[0]["roi_meta"]
            else:
                report_progress(on_progress, 25, f"Canal {channel_mode}")
                ch = self._channel_from_bgr(bgr, channel_mode)
                one = self._process_channel(ch, polygon, polygon_complement=polygon_complement)
                roi = one["roi"]
                roi_meta = one["roi_meta"]
                deriv_v = one["deriv_v"]
                deriv_h = one["deriv_h"]
                freqs_v, spec_v = one["freqs_v"], one["spec_v"]
                freqs_h, spec_h = one["freqs_h"], one["spec_h"]

            report_progress(on_progress, 75, "FFT e derivadas concluidas")
            peak_v = float(np.max(spec_v[1:])) if len(spec_v) > 1 else 0.0
            peak_h = float(np.max(spec_h[1:])) if len(spec_h) > 1 else 0.0

            report_progress(on_progress, 82, "Salvando espectros")
            result_dir = job_artifact_dir(parameters, fallback_subdir="resampling_tmp")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

            paths = {
                "original": result_dir / f"original_{stamp}.png",
                "deriv_v": result_dir / f"deriv_v_{stamp}.png",
                "deriv_h": result_dir / f"deriv_h_{stamp}.png",
                "spec_v": result_dir / f"spec_v_{stamp}.png",
                "spec_h": result_dir / f"spec_h_{stamp}.png",
                "spec_combined": result_dir / f"spec_combined_{stamp}.png",
            }

            cv2.imwrite(str(paths["original"]), _normalize_u8(roi))
            cv2.imwrite(str(paths["deriv_v"]), _normalize_u8(np.abs(deriv_v)))
            cv2.imwrite(str(paths["deriv_h"]), _normalize_u8(np.abs(deriv_h)))
            _save_spectrum_plot(paths["spec_v"], freqs_v, spec_v, "Vertical")
            _save_spectrum_plot(paths["spec_h"], freqs_h, spec_h, "Horizontal")
            _save_combined_spectrum(paths["spec_combined"], freqs_v, spec_v, freqs_h, spec_h)

            return {
                "success": True,
                "adapter": "resampling",
                "status": "completed",
                "peak_value_vertical": peak_v,
                "peak_value_horizontal": peak_h,
                "channel_mode": channel_mode,
                "is_color_input": is_color,
                "order": ORDER,
                "roi": roi_meta,
                "polygon_applied": bool(roi_meta),
                "original_crop_path": str(paths["original"]),
                "deriv_v_image_path": str(paths["deriv_v"]),
                "deriv_h_image_path": str(paths["deriv_h"]),
                "spectrum_v_image_path": str(paths["spec_v"]),
                "spectrum_h_image_path": str(paths["spec_h"]),
                "spectrum_combined_image_path": str(paths["spec_combined"]),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "resampling"}
