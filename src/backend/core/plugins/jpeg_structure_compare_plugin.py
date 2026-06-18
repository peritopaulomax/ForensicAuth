"""Comparação de estruturas JPEG entre múltiplas evidências."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.metadata.jpeg_structure_compare import build_comparison_report, build_positional_grid_report, build_similarity_matrix
from core.metadata.jpeg_structure_dump import is_jpeg_file
from core.metadata.jpeg_structure_grid_export import (
    enrich_grid_payload,
    render_grid_txt,
)
from core.metadata.jpeg_structure_matrix_export import (
    enrich_matrix_payload,
    render_matrix_png,
    render_matrix_txt,
)


class JpegStructureComparePlugin(ForensicPlugin):
    @property
    def name(self) -> str:
        return "jpeg_structure_compare"

    @property
    def supported_types(self) -> list[str]:
        return ["imagem"]

    def _validate_jpeg_paths(self, paths: list[str], ids: list[Any] | None = None) -> Tuple[bool, str]:
        if not paths:
            return False, "caminhos de evidência não resolvidos"
        for path in paths:
            if not is_jpeg_file(str(path)):
                return False, f"Arquivo não é JPEG: {Path(path).name}"
        if ids is not None and len(paths) != len(ids):
            return False, "IDs e caminhos devem ter o mesmo tamanho"
        return True, ""

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        mode = parameters.get("mode", "positional")

        if mode == "with_reference":
            q_ids = parameters.get("questioned_evidence_ids") or []
            r_ids = parameters.get("reference_evidence_ids") or []
            if not isinstance(q_ids, list) or len(q_ids) < 1:
                return False, "questioned_evidence_ids obrigatório (lista)"
            if not isinstance(r_ids, list) or len(r_ids) < 1:
                return False, "reference_evidence_ids obrigatório no modo com referência"
            ok, msg = self._validate_jpeg_paths(
                list(parameters.get("questioned_paths") or []),
                q_ids,
            )
            if not ok:
                return False, msg
            ok, msg = self._validate_jpeg_paths(
                list(parameters.get("reference_paths") or []),
                r_ids,
            )
            return (ok, msg) if ok else (False, msg)

        if mode == "all_pairs":
            q_ids = parameters.get("questioned_evidence_ids") or []
            if not isinstance(q_ids, list) or len(q_ids) < 2:
                return False, "Modo sem referência exige ao menos 2 questionados"
            return self._validate_jpeg_paths(
                list(parameters.get("questioned_paths") or []),
                q_ids,
            )

        ev_ids = parameters.get("evidence_ids") or []
        if not isinstance(ev_ids, list) or len(ev_ids) < 2:
            return False, "evidence_ids obrigatório (lista com ao menos 2 imagens JPEG)"

        paths = parameters.get("evidence_paths") or []
        ok, msg = self._validate_jpeg_paths(paths, ev_ids)
        if not ok:
            return False, msg

        ref_idx = parameters.get("reference_index", 0)
        if not isinstance(ref_idx, int) or ref_idx < 0 or ref_idx >= len(paths):
            return False, "reference_index inválido"

        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        result_dir = job_artifact_dir(parameters, fallback_subdir="jpeg_structure_compare")

        reporter = parameters.get("_progress_reporter")

        def report(pct: int, msg: str) -> None:
            if callable(reporter):
                reporter(pct, msg)

        mode = parameters.get("mode", "positional")

        if mode in ("with_reference", "all_pairs"):
            report(10, "Extraindo estruturas para matriz…")
            q_paths = list(parameters.get("questioned_paths") or [])
            q_labels = list(parameters.get("questioned_labels") or [])
            q_ids = [str(e) for e in (parameters.get("questioned_evidence_ids") or [])]
            if len(q_labels) < len(q_paths):
                q_labels.extend(Path(p).name for p in q_paths[len(q_labels) :])

            r_paths = list(parameters.get("reference_paths") or [])
            r_labels = list(parameters.get("reference_labels") or [])
            r_ids = [str(e) for e in (parameters.get("reference_evidence_ids") or [])]
            if len(r_labels) < len(r_paths):
                r_labels.extend(Path(p).name for p in r_paths[len(r_labels) :])

            payload = build_similarity_matrix(
                mode=mode,
                questioned_paths=q_paths,
                questioned_labels=q_labels,
                questioned_ids=q_ids,
                reference_paths=r_paths,
                reference_labels=r_labels,
                reference_ids=r_ids,
            )
            if not payload.get("success"):
                return {
                    "success": False,
                    "adapter": self.name,
                    "error": payload.get("error", "Matriz falhou"),
                }

            enriched = enrich_matrix_payload(
                payload,
                reference_evidence_ids=r_ids,
                questioned_evidence_ids=q_ids,
            )

            report(85, "Gerando artefatos…")
            json_path = result_dir / "jpeg_structure_matrix.json"
            png_path = result_dir / "jpeg_structure_matrix.png"
            txt_path = result_dir / "jpeg_structure_report.txt"

            with open(json_path, "w", encoding="utf-8") as fh:
                json.dump(enriched, fh, ensure_ascii=False, indent=2)

            try:
                render_matrix_png(enriched, png_path)
            except Exception as exc:
                enriched.setdefault("errors", []).append(f"Falha ao gerar PNG: {exc}")
                png_path = None

            try:
                render_matrix_txt(enriched, txt_path)
            except Exception as exc:
                enriched.setdefault("errors", []).append(f"Falha ao gerar TXT: {exc}")
                txt_path = None

            grid_base = build_positional_grid_report(
                mode=mode,
                reference_structures=enriched.get("reference_structures") or [],
                questioned_structures=enriched.get("questioned_structures") or [],
            )
            grid_enriched = enrich_grid_payload(
                grid_base,
                reference_evidence_ids=r_ids,
                questioned_evidence_ids=q_ids,
            ) if grid_base.get("success") else None

            grid_json_path = result_dir / "jpeg_structure_grid.json"
            grid_txt_path = result_dir / "jpeg_structure_grid.txt"

            if grid_enriched:
                with open(grid_json_path, "w", encoding="utf-8") as fh:
                    json.dump(grid_enriched, fh, ensure_ascii=False, indent=2)
                try:
                    render_grid_txt(grid_enriched, grid_txt_path)
                except Exception as exc:
                    enriched.setdefault("errors", []).append(f"Falha ao gerar TXT da grade: {exc}")
                    grid_txt_path = None
            else:
                grid_json_path = None
                grid_txt_path = None

            report(100, "Concluído")
            out: Dict[str, Any] = {
                "success": True,
                "adapter": self.name,
                "technique": self.name,
                "mode": mode,
                "reference_count": enriched.get("reference_count", 0),
                "questioned_count": enriched.get("questioned_count", 0),
                "matrix": enriched.get("matrix"),
                "reference_structures": enriched.get("reference_structures", []),
                "questioned_structures": enriched.get("questioned_structures", []),
                "legend": enriched.get("legend", {}),
                "criteria_version": enriched.get("criteria_version"),
                "comparison_rules": enriched.get("comparison_rules"),
                "errors": enriched.get("errors", []),
                "matrix_json_path": str(json_path),
                "matrix_report_filename": "jpeg_structure_matrix.json",
            }
            if png_path and png_path.exists() and png_path.stat().st_size > 0:
                out["matrix_image_path"] = str(png_path)
            if txt_path and txt_path.exists():
                out["matrix_report_txt_path"] = str(txt_path)
            if grid_json_path and grid_json_path.exists():
                out["grid_json_path"] = str(grid_json_path)
            if grid_txt_path and grid_txt_path.exists():
                out["grid_report_txt_path"] = str(grid_txt_path)
            return out

        paths = list(parameters.get("evidence_paths") or [])
        labels = list(parameters.get("evidence_labels") or [])
        ev_ids = [str(e) for e in (parameters.get("evidence_ids") or [])]
        ref_idx = int(parameters.get("reference_index", 0))

        if len(labels) < len(paths):
            labels.extend(Path(p).name for p in paths[len(labels) :])

        report(10, "Extraindo estruturas JPEG…")
        payload = build_comparison_report(
            paths,
            labels,
            ev_ids,
            reference_index=ref_idx,
        )

        if not payload.get("success"):
            return {
                "success": False,
                "adapter": self.name,
                "error": payload.get("error", "Comparação falhou"),
                "structures": payload.get("structures", []),
            }

        report(90, "Gerando relatório…")
        json_path = result_dir / "jpeg_structure_compare.json"
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

        report(100, "Concluído")
        return {
            "success": True,
            "adapter": self.name,
            "technique": self.name,
            "mode": "positional",
            "reference_index": payload["reference_index"],
            "reference_evidence_id": payload["reference_evidence_id"],
            "reference_label": payload["reference_label"],
            "file_count": payload["file_count"],
            "max_positions": payload["max_positions"],
            "all_match": payload["all_match"],
            "structures": payload["structures"],
            "comparisons": payload["comparisons"],
            "errors": payload.get("errors", []),
            "compare_json_path": str(json_path),
            "compare_report_filename": "jpeg_structure_compare.json",
        }
