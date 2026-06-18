"""Similaridade estrutural ISO BMFF (com/sem referencia)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.legacy.video.isom_similarity import run_similarity_analysis


class ISOMediaComparePlugin(ForensicPlugin):
    @property
    def name(self) -> str:
        return "isomedia_compare"

    @property
    def supported_types(self) -> list[str]:
        return ["video"]

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
        mode = parameters.get("mode")
        if mode not in ("with_reference", "all_pairs"):
            return False, "mode deve ser with_reference ou all_pairs"

        q_ids = parameters.get("questioned_evidence_ids") or []
        if not isinstance(q_ids, list) or len(q_ids) < 1:
            return False, "questioned_evidence_ids obrigatorio (lista)"

        if mode == "with_reference":
            r_ids = parameters.get("reference_evidence_ids") or []
            if not isinstance(r_ids, list) or len(r_ids) < 1:
                return False, "reference_evidence_ids obrigatorio no modo com referencia"
        elif mode == "all_pairs" and len(q_ids) < 2:
            return False, "Modo sem referencia exige ao menos 2 videos questionados"

        q_paths = parameters.get("questioned_paths") or []
        if mode == "with_reference":
            r_paths = parameters.get("reference_paths") or []
            if not r_paths:
                return False, "reference_paths nao resolvido"
        if not q_paths:
            return False, "questioned_paths nao resolvido"
        return True, ""

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        tmpdir = job_artifact_dir(parameters, fallback_subdir="isom_sim_tmp")
        reporter = parameters.get("_progress_reporter")

        def report(pct: int, msg: str) -> None:
            if callable(reporter):
                reporter(pct, msg)

        try:
            mode = str(parameters.get("mode"))
            ref_paths = list(parameters.get("reference_paths") or [])
            ref_labels = list(parameters.get("reference_labels") or [])
            quest_paths = list(parameters.get("questioned_paths") or [])
            quest_labels = list(parameters.get("questioned_labels") or [])

            if len(ref_labels) < len(ref_paths):
                ref_labels.extend(Path(p).name for p in ref_paths[len(ref_labels) :])
            if len(quest_labels) < len(quest_paths):
                quest_labels.extend(Path(p).name for p in quest_paths[len(quest_labels) :])

            out = run_similarity_analysis(
                mode=mode,
                reference_paths=ref_paths,
                reference_labels=ref_labels,
                questioned_paths=quest_paths,
                questioned_labels=quest_labels,
                out_dir=tmpdir,
                reporter=report,
            )
            payload = out.get("similarity_payload") or {}
            return {
                "success": True,
                "adapter": self.name,
                "status": "completed",
                "mode": mode,
                "reference_count": len(ref_paths),
                "questioned_count": len(quest_paths),
                "pair_differences": out.get("pair_differences"),
                "similarity_payload": payload,
                "similarity_json_path": out.get("similarity_json_path"),
                "similarity_jaccard_image_path": out.get("similarity_jaccard_image_path"),
                "similarity_wl_kernel_image_path": out.get("similarity_wl_kernel_image_path"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "adapter": self.name}
