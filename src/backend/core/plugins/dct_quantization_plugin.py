"""DCT quantization matrix estimation and artifact analysis plugin.

Supports three modes:
1. estimate: Estimates Q-matrix from evidence and generates artifact heatmap
2. reference: Reads Q-matrix from a reference JPEG and compares with evidence
3. custom: Applies a user-provided 8x8 quantization matrix and generates artifact heatmap
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
from PIL import Image

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir


class DCTQuantizationPlugin(ForensicPlugin):
    """JPEG DCT quantization matrix analysis with legacy artifact processing."""

    @property
    def name(self) -> str:
        return "dct_quantization"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        mode = parameters.get("mode", "estimate")
        if mode not in ("estimate", "reference", "custom"):
            return False, "mode must be one of: estimate, reference, custom"

        if mode == "reference":
            if not parameters.get("reference_path"):
                return False, "reference_path is required for reference mode"

        if mode == "custom":
            qm = parameters.get("quantization_matrix")
            if not qm or not isinstance(qm, list) or len(qm) != 8:
                return False, "quantization_matrix must be an 8x8 list of lists"
            for row in qm:
                if not isinstance(row, list) or len(row) != 8:
                    return False, "quantization_matrix must be an 8x8 list of lists"

        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        mode = parameters.get("mode", "estimate")
        result_dir = job_artifact_dir(parameters, fallback_subdir="dct_quantization")

        if mode == "estimate":
            return self._mode_estimate(evidence_path, result_dir)
        elif mode == "reference":
            ref_path = parameters.get("reference_path", "")
            return self._mode_reference(evidence_path, ref_path, result_dir)
        elif mode == "custom":
            qm = parameters.get("quantization_matrix", [])
            return self._mode_custom(evidence_path, qm, result_dir)

        return {"success": False, "error": f"Unknown mode: {mode}"}

    def _mode_estimate(self, evidence_path: str, result_dir: Path) -> Dict[str, Any]:
        from core.legacy.dct.estimativaq import estimativaq

        try:
            MatrizQ = estimativaq(evidence_path)
            estimated_path = self._save_matrix_image(
                MatrizQ, result_dir, "estimated", title="Matriz estimada (estimativaq)"
            )
            artifact_path = self._process_artifacts(evidence_path, MatrizQ, result_dir, "estimate")

            payload: Dict[str, Any] = {
                "success": True,
                "mode": "estimate",
                "quantization_matrix": MatrizQ.tolist(),
                "matrix_image_path": str(estimated_path),
                "estimated_matrix_image_path": str(estimated_path),
                "artifact_image_path": str(artifact_path),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            jpegio_matrix = self._try_read_jpeg_matrix(evidence_path)
            if jpegio_matrix is not None:
                jpegio_path = self._save_matrix_image(
                    jpegio_matrix,
                    result_dir,
                    "jpegio",
                    title="Matriz lida do JPEG (jpegio)",
                )
                payload["jpegio_matrix"] = jpegio_matrix.tolist()
                payload["jpegio_matrix_image_path"] = str(jpegio_path)
            return payload
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _mode_reference(self, evidence_path: str, ref_path: str, result_dir: Path) -> Dict[str, Any]:
        from core.legacy.dct.estimativaq import estimativaq

        try:
            MatrizQ_ev = estimativaq(evidence_path)

            # For JPEG references, require direct quantization table read via jpegio.
            # This avoids silent fallback to estimation, which may yield zeros/unreliable values.
            ref_ext = Path(ref_path).suffix.lower()
            if ref_ext in (".jpg", ".jpeg"):
                MatrizQ_ref = self._read_jpeg_matrix(ref_path)
                matrix_source = "jpegio"
            else:
                MatrizQ_ref = estimativaq(ref_path)
                matrix_source = "estimated_non_jpeg_reference"

            # Compute matrix difference (numeric only; no comparison PNG)
            diff = np.abs(MatrizQ_ev - MatrizQ_ref)

            # Process artifacts with reference matrix
            artifact_path = self._process_artifacts(evidence_path, MatrizQ_ref, result_dir, "reference")

            estimated_path = self._save_matrix_image(
                MatrizQ_ev, result_dir, "estimated", title="Matriz estimada da evidencia"
            )

            payload: Dict[str, Any] = {
                "success": True,
                "mode": "reference",
                "evidence_matrix": MatrizQ_ev.tolist(),
                "reference_matrix": MatrizQ_ref.tolist(),
                "reference_matrix_source": matrix_source,
                "difference_matrix": diff.tolist(),
                "mean_difference": float(np.mean(diff)),
                "estimated_matrix_image_path": str(estimated_path),
                "matrix_image_path": str(estimated_path),
                "artifact_image_path": str(artifact_path),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            evidence_jpegio = self._try_read_jpeg_matrix(evidence_path)
            if evidence_jpegio is not None:
                jpegio_path = self._save_matrix_image(
                    evidence_jpegio,
                    result_dir,
                    "jpegio",
                    title="Matriz lida do JPEG da evidencia (jpegio)",
                )
                payload["evidence_jpegio_matrix"] = evidence_jpegio.tolist()
                payload["jpegio_matrix_image_path"] = str(jpegio_path)
            return payload
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _mode_custom(self, evidence_path: str, qm: list, result_dir: Path) -> Dict[str, Any]:
        from core.legacy.dct.estimativaq import estimativaq

        try:
            # Estimate actual matrix from evidence
            MatrizQ_actual = estimativaq(evidence_path)

            # Convert user matrix to numpy
            MatrizQ_custom = np.array(qm, dtype=np.float64)

            # Compare matrices (numeric only; no comparison PNG)
            diff = np.abs(MatrizQ_actual - MatrizQ_custom)

            # Process artifacts with custom matrix
            artifact_path = self._process_artifacts(evidence_path, MatrizQ_custom, result_dir, "custom")

            estimated_path = self._save_matrix_image(
                MatrizQ_actual, result_dir, "estimated", title="Matriz estimada da evidencia"
            )

            payload: Dict[str, Any] = {
                "success": True,
                "mode": "custom",
                "actual_matrix": MatrizQ_actual.tolist(),
                "custom_matrix": MatrizQ_custom.tolist(),
                "difference_matrix": diff.tolist(),
                "mean_difference": float(np.mean(diff)),
                "estimated_matrix_image_path": str(estimated_path),
                "matrix_image_path": str(estimated_path),
                "artifact_image_path": str(artifact_path),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            jpegio_matrix = self._try_read_jpeg_matrix(evidence_path)
            if jpegio_matrix is not None:
                jpegio_path = self._save_matrix_image(
                    jpegio_matrix,
                    result_dir,
                    "jpegio",
                    title="Matriz lida do JPEG (jpegio)",
                )
                payload["jpegio_matrix"] = jpegio_matrix.tolist()
                payload["jpegio_matrix_image_path"] = str(jpegio_path)
            return payload
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _is_jpeg(self, path: str) -> bool:
        return Path(path).suffix.lower() in (".jpg", ".jpeg")

    def _try_read_jpeg_matrix(self, path: str) -> np.ndarray | None:
        """Best-effort jpegio read for supplemental display; returns None if unavailable."""
        if not self._is_jpeg(path):
            return None
        try:
            return self._read_jpeg_matrix(path)
        except Exception:
            return None

    def _read_jpeg_matrix(self, ref_path: str) -> np.ndarray:
        """Read quantization table from JPEG file via jpegio (strict)."""
        if not self._is_jpeg(ref_path):
            raise ValueError("Arquivo nao e JPEG para leitura direta de matriz")

        try:
            import jpegio as jio
        except Exception as exc:
            raise RuntimeError(
                "jpegio nao disponivel no ambiente; leitura direta da matriz JPEG de referencia indisponivel"
            ) from exc

        try:
            I_struct = jio.read(ref_path)
            qt = I_struct.quant_tables[0] if I_struct.quant_tables else None
        except Exception as exc:
            raise RuntimeError(f"Falha ao ler tabela de quantizacao JPEG com jpegio: {exc}") from exc

        if qt is None:
            raise RuntimeError("JPEG de referencia sem quantization table (quant_tables[0] ausente)")

        matrix = np.array(qt, dtype=np.float64)
        if matrix.shape != (8, 8):
            raise RuntimeError(f"Tabela de quantizacao invalida: shape {matrix.shape}, esperado (8, 8)")
        if np.any(matrix <= 0):
            raise RuntimeError("Tabela de quantizacao JPEG invalida: valores <= 0 encontrados")
        return matrix

    def _process_artifacts(self, image_path: str, MatrizQ: np.ndarray, result_dir: Path, prefix: str) -> Path:
        """Legacy DCT artifact processing pipeline.

        1. Convert image to luminance Y
        2. Crop to multiple of 8, subtract 128
        3. Apply DCT block-by-block
        4. Compute BMat = abs(YDCT - round(YDCT/D)*D)
        5. Aggregate per 8x8 block → BMat_matriz
        6. Save as heatmap image
        """
        # Load image
        im = np.array(Image.open(image_path))
        im = np.double(im)

        # Convert to luminance
        if im.ndim == 3:
            Y = 0.299 * im[:, :, 0] + 0.587 * im[:, :, 1] + 0.114 * im[:, :, 2]
        else:
            Y = im

        # Adjust to multiple of 8
        linhas, colunas = Y.shape
        Y = Y[:linhas - (linhas % 8), :colunas - (colunas % 8)]
        Y = Y - 128

        # Matriz DCT T (referencia Popescu & Farid)
        T = np.array([
            [0.3536, 0.3536, 0.3536, 0.3536, 0.3536, 0.3536, 0.3536, 0.3536],
            [0.4904, 0.4157, 0.2778, 0.0975, -0.0975, -0.2778, -0.4157, -0.4904],
            [0.4619, 0.1913, -0.1913, -0.4619, -0.4619, -0.1913, 0.1913, 0.4619],
            [0.4157, -0.0975, -0.4904, -0.2778, 0.2778, 0.4904, 0.0975, -0.4157],
            [0.3536, -0.3536, -0.3536, 0.3536, 0.3536, -0.3536, -0.3536, 0.3536],
            [0.2778, -0.4904, 0.0975, 0.4157, -0.4157, -0.0975, 0.4904, -0.2778],
            [0.1913, -0.4619, 0.4619, -0.1913, -0.1913, 0.4619, -0.4619, 0.1913],
            [0.0975, -0.2778, 0.4157, -0.4904, 0.4904, -0.4157, 0.2778, -0.0975],
        ])

        # Apply DCT block-by-block
        imSize = Y.shape
        YDCT = np.zeros_like(Y)
        for i in range(0, imSize[0], 8):
            for j in range(0, imSize[1], 8):
                bloco = Y[i:i+8, j:j+8]
                YDCT[i:i+8, j:j+8] = np.round(T @ bloco @ T.T)

        # Tile quantization matrix to image size
        D = np.tile(MatrizQ, (imSize[0] // 8, imSize[1] // 8))

        # Compute artifact residue: BMat = abs(YDCT - round(YDCT/D)*D)
        with np.errstate(divide="ignore", invalid="ignore"):
            BMat = np.abs(YDCT - np.round(YDCT / D) * D)
        BMat[np.isnan(BMat)] = 0

        # Aggregate per 8x8 block
        BMat_matriz = np.zeros((imSize[0] // 8, imSize[1] // 8))
        for i in range(imSize[0] // 8):
            for j in range(imSize[1] // 8):
                bloco = BMat[i*8:(i+1)*8, j*8:(j+1)*8]
                BMat_matriz[i, j] = np.mean(bloco)

        # Save heatmap (block-level, small)
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 8))
        im_plot = ax.imshow(BMat_matriz, cmap="hot", interpolation="nearest")
        ax.set_title("DCT Quantization Artifacts")
        fig.colorbar(im_plot, ax=ax)
        plt.tight_layout()
        path = result_dir / f"{prefix}_artifacts.png"
        fig.savefig(str(path), dpi=150)
        plt.close(fig)

        # Save upscaled artifact map (8x nearest-neighbor) for side-by-side preview
        # Normalize BMat_matriz to 0-255 for PNG
        bmin, bmax = BMat_matriz.min(), BMat_matriz.max()
        if bmax > bmin:
            normed = ((BMat_matriz - bmin) / (bmax - bmin) * 255).astype(np.uint8)
        else:
            normed = np.zeros_like(BMat_matriz, dtype=np.uint8)

        pil_img = Image.fromarray(normed, mode="L")
        upscaled = pil_img.resize((imSize[1], imSize[0]), Image.NEAREST)
        upscaled_path = result_dir / f"{prefix}_artifacts_upscaled.png"
        upscaled.save(str(upscaled_path))

        return upscaled_path

    def _save_matrix_image(
        self,
        matrix: np.ndarray,
        result_dir: Path,
        prefix: str,
        *,
        title: str = "Quantization Matrix",
    ) -> Path:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(6, 6))
        im = ax.imshow(matrix, cmap="viridis", interpolation="nearest")
        ax.set_title(title)
        for i in range(8):
            for j in range(8):
                ax.text(j, i, f"{int(matrix[i, j])}", ha="center", va="center", color="white", fontsize=8)
        fig.colorbar(im, ax=ax)
        plt.tight_layout()
        path = result_dir / f"{prefix}_matrix.png"
        fig.savefig(str(path), dpi=150)
        plt.close(fig)
        return path
