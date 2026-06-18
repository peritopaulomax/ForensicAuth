"""PRNU (Photo Response Non-Uniformity) adapter — camera fingerprint matching.

Wraps the legacy PRNU pipeline from Goljan et al. (SPIE 2009):
  - Noise extraction via wavelet domain (Filter.py)
  - Cross-correlation and PCE computation (Functions.py, maindir.py)
  - Fingerprint generation from reference images (getFingerprint.py)

The legacy code is kept intact under core/legacy/prnu/;
only import paths and I/O wrappers were adapted.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
import plotly.graph_objects as go

from app.config import get_settings
from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir


def _json_safe(value: Any) -> Any:
    """Convert numpy scalars/arrays to native Python types for json.dump."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, np.generic):
        if isinstance(value, np.floating):
            return float(value)
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.bool_):
            return bool(value)
    return value


# Colormap da superficie de correlacao (azul → branco → verde → vermelho)
_PRNU_SURFACE_COLORSCALE = [
    [0.0, "rgb(0, 0, 255)"],
    [0.4, "rgb(255, 255, 255)"],
    [0.7, "rgb(0, 160, 0)"],
    [1.0, "rgb(255, 0, 0)"],
]


class PRNUAdapter(ForensicPlugin):
    """PRNU-based camera fingerprint matching."""

    @property
    def name(self) -> str:
        return "prnu"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        has_fp = any(
            k in parameters
            for k in ("fingerprint_path", "camera_id", "fingerprint_id")
        )
        if not has_fp:
            return False, "Requer fingerprint_path, camera_id ou fingerprint_id"
        if "fingerprint_id" in parameters and "case_id" not in parameters:
            return False, "fingerprint_id requer case_id"
        mode = parameters.get("mode", "full")
        if mode not in ("full", "cropped", "scaled"):
            return False, "mode deve ser 'full', 'cropped' ou 'scaled'"
        return True, ""

    def _get_fingerprint_path(self, parameters: Dict[str, Any]) -> Path:
        if "fingerprint_path" in parameters:
            return Path(parameters["fingerprint_path"])
        camera_id = parameters.get("camera_id")
        settings = get_settings()
        return Path(settings.MODELS_DIR) / "prnu" / "fingerprints" / f"{camera_id}.npy"

    @staticmethod
    def _progress_cb(parameters: Dict[str, Any]) -> Optional[Callable[[int, str], None]]:
        cb = parameters.get("_progress")
        return cb if callable(cb) else None

    @staticmethod
    def _peak_indices_fftshift(peak_loc: Any, shape: Tuple[int, int]) -> Tuple[int, int]:
        """Map PeakLocation in C to indices after np.fft.fftshift (centro = lag [0,0])."""
        pr, pc = int(peak_loc[0]), int(peak_loc[1])
        nr, nc = shape[0], shape[1]
        return (pr + nr // 2) % nr, (pc + nc // 2) % nc

    @staticmethod
    def _save_correlation_surface_html(
        C: np.ndarray,
        peak_loc: Any,
        pce: float,
        mode: str,
        out_path: Path,
        half_window: int = 160,
    ) -> None:
        """Superficie 3D interativa (Plotly): Z = fftshift(C), recorte no pico."""
        Z_full = np.fft.fftshift(np.squeeze(C).astype(np.float64))
        h, w = Z_full.shape
        sr, sc = PRNUAdapter._peak_indices_fftshift(peak_loc, (h, w))

        if h <= 2 * half_window + 1 and w <= 2 * half_window + 1:
            Z = Z_full
            r0, c0 = 0, 0
            crop_note = "superficie completa"
        else:
            r0 = max(0, sr - half_window)
            r1 = min(h, sr + half_window + 1)
            c0 = max(0, sc - half_window)
            c1 = min(w, sc + half_window + 1)
            Z = Z_full[r0:r1, c0:c1]
            crop_note = f"recorte ±{half_window} px ao redor do pico"

        pk_r, pk_c = sr - r0, sc - c0
        z_peak = float(Z[pk_r, pk_c])

        rows = np.arange(Z.shape[0])
        cols = np.arange(Z.shape[1])

        surface = go.Surface(
            x=cols,
            y=rows,
            z=Z,
            colorscale=_PRNU_SURFACE_COLORSCALE,
            colorbar=dict(title="C (correlacao)"),
            contours={
                "z": {
                    "show": True,
                    "usecolormap": True,
                    "project": {"z": True},
                    "width": 2,
                }
            },
            name="fftshift(C)",
        )

        peak_marker = go.Scatter3d(
            x=[pk_c],
            y=[pk_r],
            z=[z_peak],
            mode="markers",
            marker=dict(size=7, color="black", symbol="diamond"),
            showlegend=False,
            hovertext=[f"Pico PCE={pce:.2g}"],
            hoverinfo="text",
        )

        traces: List[Any] = [surface, peak_marker]

        center_r, center_c = h // 2, w // 2
        cr, cc = center_r - r0, center_c - c0
        if 0 <= cr < Z.shape[0] and 0 <= cc < Z.shape[1]:
            traces.append(
                go.Scatter3d(
                    x=[cc],
                    y=[cr],
                    z=[float(Z[cr, cc])],
                    mode="markers",
                    marker=dict(size=6, color="cyan", symbol="cross"),
                    showlegend=False,
                    hovertext=["Lag [0,0] em C"],
                    hoverinfo="text",
                )
            )

        pr0, pc0 = int(peak_loc[0]), int(peak_loc[1])
        fig = go.Figure(data=traces)
        fig.update_layout(
            title=dict(
                text=f"Superficie C (fftshift) · modo {mode} · PCE={pce:.4g} · pico C[{pr0},{pc0}]",
                x=0.5,
                xanchor="center",
                font=dict(size=14),
            ),
            height=760,
            showlegend=False,
            scene=dict(
                xaxis_title="Deslocamento Y",
                yaxis_title="Deslocamento X",
                zaxis_title="Correlacao",
                aspectmode="manual",
                aspectratio=dict(x=1, y=1, z=0.5),
                camera=dict(eye=dict(x=1.7, y=1.7, z=1.15)),
            ),
            margin=dict(l=0, r=0, t=72, b=8),
            annotations=[
                dict(
                    text=crop_note + " · gire/zoom com o mouse",
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=1.01,
                    showarrow=False,
                    font=dict(size=11, color="#4b5563"),
                )
            ],
        )

        fig.write_html(
            str(out_path),
            include_plotlyjs="cdn",
            div_id="prnu-correlation-surface",
            config={
                "scrollZoom": True,
                "displayModeBar": True,
                "displaylogo": False,
                "responsive": True,
            },
        )

    @staticmethod
    def _save_jet_array(arr: np.ndarray, out_path: Path) -> None:
        surf = np.squeeze(arr).astype(np.float64)
        surf = surf - np.nanmin(surf)
        mx = float(np.nanmax(surf))
        if mx > 0:
            surf = surf / mx
        u8 = (np.clip(surf, 0.0, 1.0) * 255).astype(np.uint8)
        cv2.imwrite(str(out_path), cv2.applyColorMap(u8, cv2.COLORMAP_JET))

    @staticmethod
    def _save_scale_curve(scale_curve: List[Dict[str, float]], out_path: Path) -> None:
        if not scale_curve:
            return
        scales = [p["scale"] for p in scale_curve]
        pces = [p["pce"] for p in scale_curve]
        fig, ax = plt.subplots(figsize=(8, 4), dpi=120)
        ax.plot(scales, pces, color="#2563eb", linewidth=1.5)
        ax.set_xlabel("Fator de escala (1/r)")
        ax.set_ylabel("PCE")
        ax.set_title("PCE vs escala (modo redimensionado)")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(out_path, bbox_inches="tight")
        plt.close(fig)

    def _run_full(
        self, prnu_legacy, Noisex: np.ndarray, Fingerprint: np.ndarray
    ) -> Tuple[np.ndarray, Dict[str, Any], Optional[Dict[str, Any]]]:
        C = prnu_legacy.crosscorr(Noisex, Fingerprint)
        det, det0 = prnu_legacy.PCE(C)
        return C, det, det0

    def _run_cropped(
        self,
        prnu_legacy,
        Noisex: np.ndarray,
        Fingerprint: np.ndarray,
        Ix: np.ndarray,
    ) -> Tuple[np.ndarray, Dict[str, Any], Optional[Dict[str, Any]]]:
        if Fingerprint.shape[0] > Noisex.shape[0] or Fingerprint.shape[1] > Noisex.shape[1]:
            A = np.pad(
                Noisex,
                [
                    (0, abs(2 * Fingerprint.shape[0] - 1 - Noisex.shape[0])),
                    (0, abs(2 * Fingerprint.shape[1] - 1 - Noisex.shape[1])),
                ],
            )
            F = np.pad(
                Fingerprint,
                [
                    (0, abs(Fingerprint.shape[0] - 1)),
                    (0, abs(Fingerprint.shape[1] - 1)),
                ],
            )
        else:
            A = Noisex
            F = Fingerprint

        C = prnu_legacy.crosscorr(A, F)
        det, det0 = prnu_legacy.PCE(
            C,
            [Fingerprint.shape[0] - Noisex.shape[0], Fingerprint.shape[1] - Noisex.shape[1]],
            11,
        )
        loc = det["PeakLocation"]
        C = prnu_legacy.crosscorr(
            Noisex,
            Fingerprint[loc[0] : loc[0] + Ix.shape[0], loc[1] : loc[1] + Ix.shape[1]],
        )
        det, det0 = prnu_legacy.PCE(C)
        return C, det, det0

    def _run_scaled(
        self,
        prnu_legacy,
        Noisex: np.ndarray,
        Fingerprint: np.ndarray,
        progress: Optional[Callable[[int, str], None]],
    ) -> Tuple[np.ndarray, Dict[str, Any], Optional[Dict[str, Any]], List[Dict[str, float]], float]:
        best_det: Optional[Dict[str, Any]] = None
        best_scale = 1.0
        best_C: Optional[np.ndarray] = None
        scale_curve: List[Dict[str, float]] = []
        rmin = 0.5
        esc_max = 1.5
        passo = 0.05
        scales = list(np.arange(rmin, esc_max + passo, passo))
        total = len(scales)

        for idx, rinv in enumerate(scales):
            if progress and idx % 3 == 0:
                pct = 35 + int(45 * idx / max(total, 1))
                progress(pct, f"Busca de escala ({idx + 1}/{total})")

            F_scaled = cv2.resize(
                Fingerprint,
                None,
                fx=1 / rinv,
                fy=1 / rinv,
                interpolation=cv2.INTER_LINEAR,
            )
            if F_scaled.shape[0] > Noisex.shape[0] or F_scaled.shape[1] > Noisex.shape[1]:
                A = np.pad(
                    Noisex,
                    [
                        (0, abs(2 * F_scaled.shape[0] - 1 - Noisex.shape[0])),
                        (0, abs(2 * F_scaled.shape[1] - 1 - Noisex.shape[1])),
                    ],
                )
            else:
                A = Noisex

            C_try = prnu_legacy.crosscorr(A, F_scaled)
            det_try, _ = prnu_legacy.PCE(
                C_try,
                [F_scaled.shape[0] - Noisex.shape[0], F_scaled.shape[1] - Noisex.shape[1]],
                11,
            )
            pce_val = float(det_try.get("PCE", 0))
            scale_curve.append({"scale": round(float(rinv), 3), "pce": round(pce_val, 4)})

            if best_det is None or pce_val > float(best_det.get("PCE", 0)):
                best_det = det_try
                best_scale = float(rinv)
                best_C = C_try

        assert best_det is not None and best_C is not None
        return best_C, best_det, None, scale_curve, best_scale

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        from core.legacy import prnu as prnu_legacy

        progress = self._progress_cb(parameters)
        if progress:
            progress(5, "Carregando fingerprint")

        fp_path = self._get_fingerprint_path(parameters)
        if not fp_path.exists():
            return {
                "success": False,
                "error": f"Fingerprint nao encontrado: {fp_path}",
                "adapter": "prnu",
            }

        try:
            Fingerprint = np.load(fp_path)
        except Exception as exc:
            return {
                "success": False,
                "error": f"Falha ao carregar fingerprint: {exc}",
                "adapter": "prnu",
            }

        Ix = cv2.imread(evidence_path)
        if Ix is None:
            return {"success": False, "error": "Falha ao carregar imagem", "adapter": "prnu"}

        if Ix.ndim == 3:
            Ix = Ix[:, :, ::-1]

        sigma = float(parameters.get("sigma", 2.0))
        mode = parameters.get("mode", "full")
        scale_curve: List[Dict[str, float]] = []
        best_scale: Optional[float] = None

        if parameters.get("localized_only"):
            return self._analyze_localized_only(
                evidence_path=evidence_path,
                parameters=parameters,
                Fingerprint=Fingerprint,
                Ix=Ix,
                sigma=sigma,
                progress=progress,
            )

        try:
            if progress:
                progress(12, "Carregando imagem questionada")
            if progress:
                progress(22, "Extraindo ruido PRNU (wavelet + Wiener)")
            Noisex = prnu_legacy.NoiseExtractFromImage(evidence_path, sigma=sigma)
            Noisex = prnu_legacy.WienerInDFT(Noisex, np.std(Noisex))

            if Fingerprint.ndim == 3:
                Fingerprint = prnu_legacy.rgb2gray1(Fingerprint)

            Noisex = Noisex.astype(np.float64)
            Fingerprint = Fingerprint.astype(np.float64)

            if progress:
                progress(38, f"Correlacao global (modo {mode})")

            det0: Optional[Dict[str, Any]] = None
            if mode == "full":
                C, det, det0 = self._run_full(prnu_legacy, Noisex, Fingerprint)
            elif mode == "cropped":
                C, det, det0 = self._run_cropped(prnu_legacy, Noisex, Fingerprint, Ix)
            elif mode == "scaled":
                C, det, det0, scale_curve, best_scale = self._run_scaled(
                    prnu_legacy, Noisex, Fingerprint, progress
                )
            else:
                return {"success": False, "error": f"Modo desconhecido: {mode}", "adapter": "prnu"}

        except Exception as exc:
            return {
                "success": False,
                "error": f"Erro na analise PRNU: {exc}",
                "adapter": "prnu",
            }

        pce_value = float(det.get("PCE", 0))
        peak_loc = det.get("PeakLocation", [0, 0])
        if hasattr(peak_loc, "tolist"):
            peak_loc = peak_loc.tolist()

        if progress:
            progress(68, "Montando superficie 3D da correlacao C")

        tmpdir = job_artifact_dir(parameters, fallback_subdir="prnu_tmp")
        surface_html_path = tmpdir / "correlation_surface.html"
        self._save_correlation_surface_html(C, peak_loc, pce_value, mode, surface_html_path)

        scale_curve_path: Optional[str] = None
        if mode == "scaled" and scale_curve:
            sc_path = tmpdir / "scale_curve.png"
            self._save_scale_curve(scale_curve, sc_path)
            scale_curve_path = str(sc_path)

        localized_paths: Dict[str, str] = {}
        if parameters.get("localized_map", True):
            try:
                if Noisex.shape == Fingerprint.shape:
                    if progress:
                        progress(82, "Mapa PRNU localizado — correlacao por blocos")
                    from core.legacy.prnu import localized as prnu_loc

                    igr = cv2.imread(evidence_path, cv2.IMREAD_GRAYSCALE)
                    if igr is None:
                        igr = np.squeeze(Ix)
                    block_half = int(parameters.get("block_half", 32))
                    overlap_k = int(parameters.get("overlap_k", 50))
                    n_jobs_loc = get_settings().PRNU_LOCALIZED_N_JOBS
                    pos_threshold = float(parameters.get("localized_threshold", 0.0))
                    mapa, mapa_pos, overlay = prnu_loc.localized_maps(
                        Noisex,
                        Fingerprint,
                        igr,
                        block_half=block_half,
                        overlap_k=overlap_k,
                        n_jobs=n_jobs_loc,
                        pos_threshold=pos_threshold,
                    )
                    loc_map = tmpdir / "localized_map.png"
                    loc_pos = tmpdir / "localized_positive.png"
                    loc_ov = tmpdir / "localized_overlay.png"
                    self._save_jet_array(mapa, loc_map)
                    self._save_jet_array(mapa_pos, loc_pos)
                    ov_u8 = (np.clip(overlay, 0, 1) * 255).astype(np.uint8)
                    cv2.imwrite(str(loc_ov), ov_u8)
                    localized_paths = {
                        "localized_map_image_path": str(loc_map),
                        "localized_positive_image_path": str(loc_pos),
                        "localized_overlay_image_path": str(loc_ov),
                    }
                else:
                    localized_paths["localized_skipped"] = "tamanhos diferentes"
            except Exception as loc_exc:
                localized_paths["localized_error"] = str(loc_exc)

        result: Dict[str, Any] = {
            "success": True,
            "adapter": "prnu",
            "status": "completed",
            "mode": mode,
            "sigma": sigma,
            "fingerprint_path": str(fp_path),
            "pce": round(pce_value, 4),
            "p_value": float(det.get("pvalue", 1)),
            "p_fa": float(det.get("P_FA", 1)),
            "log10_p_fa": float(det.get("log10P_FA", 0)),
            "peak_location": peak_loc,
            "peak_height": float(det.get("peakheight", 0)),
            "correlation_surface_html_path": str(surface_html_path),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if det0 is not None:
            result["pce_no_crop"] = round(float(det0.get("PCE", 0)), 4)

        if mode == "scaled":
            result["best_scale"] = best_scale
            result["scale_curve"] = scale_curve
            if scale_curve_path:
                result["scale_curve_image_path"] = scale_curve_path

        result.update(localized_paths)

        if progress:
            progress(92, "Persistindo artefatos do job")
            progress(98, "PRNU concluido")

        return _json_safe(result)

    def _analyze_localized_only(
        self,
        *,
        evidence_path: str,
        parameters: Dict[str, Any],
        Fingerprint: np.ndarray,
        Ix: np.ndarray,
        sigma: float,
        progress: Optional[Callable[[int, str], None]],
    ) -> Dict[str, Any]:
        """Reprocessa apenas mapas localizados (sem correlacao global / 3D)."""
        from core.legacy import prnu as prnu_legacy
        from core.legacy.prnu import localized as prnu_loc

        if progress:
            progress(15, "Extraindo ruido PRNU para mapa localizado")
        try:
            Noisex = prnu_legacy.NoiseExtractFromImage(evidence_path, sigma=sigma)
            Noisex = prnu_legacy.WienerInDFT(Noisex, np.std(Noisex))
            if Fingerprint.ndim == 3:
                Fingerprint = prnu_legacy.rgb2gray1(Fingerprint)
            Noisex = Noisex.astype(np.float64)
            Fingerprint = Fingerprint.astype(np.float64)

            if Noisex.shape != Fingerprint.shape:
                return {
                    "success": False,
                    "error": "Dimensoes do ruido e fingerprint incompativeis para mapa localizado",
                    "adapter": "prnu",
                }

            if progress:
                progress(45, "Correlacao por blocos (paralelo)")

            igr = cv2.imread(evidence_path, cv2.IMREAD_GRAYSCALE)
            if igr is None:
                igr = np.squeeze(Ix)

            block_half = int(parameters.get("block_half", 32))
            overlap_k = int(parameters.get("overlap_k", 50))
            n_jobs_loc = get_settings().PRNU_LOCALIZED_N_JOBS
            pos_threshold = float(parameters.get("localized_threshold", 0.0))

            mapa, mapa_pos, overlay = prnu_loc.localized_maps(
                Noisex,
                Fingerprint,
                igr,
                block_half=block_half,
                overlap_k=overlap_k,
                n_jobs=n_jobs_loc,
                pos_threshold=pos_threshold,
            )

            if progress:
                progress(88, "Salvando mapas localizados")

            tmpdir = job_artifact_dir(parameters, fallback_subdir="prnu_loc_tmp")
            loc_map = tmpdir / "localized_map.png"
            loc_pos = tmpdir / "localized_positive.png"
            loc_ov = tmpdir / "localized_overlay.png"
            self._save_jet_array(mapa, loc_map)
            self._save_jet_array(mapa_pos, loc_pos)
            ov_u8 = (np.clip(overlay, 0, 1) * 255).astype(np.uint8)
            cv2.imwrite(str(loc_ov), ov_u8)

            if progress:
                progress(98, "Mapa localizado concluido")

            return _json_safe(
                {
                    "success": True,
                    "adapter": "prnu",
                    "status": "completed",
                    "localized_only": True,
                    "block_half": block_half,
                    "overlap_k": overlap_k,
                    "localized_threshold": pos_threshold,
                    "localized_map_image_path": str(loc_map),
                    "localized_positive_image_path": str(loc_pos),
                    "localized_overlay_image_path": str(loc_ov),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": "prnu"}

    def generate_fingerprint(
        self,
        image_paths: list[str],
        output_path: str,
        sigma: float = 3.0,
    ) -> Dict[str, Any]:
        """Generate a camera fingerprint from reference images."""
        from core.legacy import prnu as prnu_legacy

        try:
            RP, _LP, used_images = prnu_legacy.getFingerprint(image_paths, sigma=sigma)
            np.save(output_path, RP)
            return {
                "success": True,
                "fingerprint_path": output_path,
                "images_used": len(used_images),
                "shape": list(RP.shape),
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }
