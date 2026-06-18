"""Save analysis artifacts as derived evidence with custody chain registration."""

import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from models.analysis_job import AnalysisJob
from models.evidence import Evidence
from services.custody_service import CustodyService
from services.derivation_contract import (
    build_derivation_metadata,
    build_operation,
    build_output,
    build_provenance_snapshot,
    compute_sha256_input,
    compute_sha256_params,
    parent_ref_from_evidence,
    provenance_to_custody_details,
)
from core.preview_effective import (
    load_job_result_json as _load_result_json_from_dir,
    merge_effective_parameters,
    persist_effective_parameters,
    record_promoted_derivative,
    sync_job_parameters,
    sync_job_runtime_receipt,
)
from core.preview_materialize import materialize_preview_artifact
from core.reproducibility import (
    build_promoted_reproducibility_record,
    load_job_execution_receipt,
)
from services.derivation_lineage import DerivationLineageBuilder


class DerivativeSaveError(Exception):
    """Raised when saving a derivative fails validation."""


class DerivativeService:
    """Persist job artifacts as derived evidences."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    @staticmethod
    def _compute_sha256(path: Path) -> str:
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _procedure_summary(self, job: AnalysisJob) -> str:
        params = job.parameters or {}
        if job.technique == "ela":
            parts = ["ELA"]
            channel = params.get("channel_mode")
            if channel:
                parts.append(str(channel).upper())
            if "quality" in params:
                parts.append(f"Q{params['quality']}")
            if "gain" in params:
                parts.append(f"G{params['gain']}")
            return " · ".join(parts)
        if job.technique == "metadata":
            return "Metadados e estrutura JPEG"
        if job.technique == "audio_spectrogram":
            params = job.parameters or {}
            parts = ["Espectrograma STFT"]
            if params.get("window_type"):
                parts.append(str(params["window_type"]))
            if params.get("fft_points") is not None:
                parts.append(f"2^{params['fft_points']}")
            return " · ".join(parts)
        return job.technique.upper()

    @staticmethod
    def _file_type_and_mime_for_derivative(
        ext: str, parent: Evidence
    ) -> tuple[str, str | None]:
        """Map artifact extension to derivative file_type/mime (fallback: parent)."""
        mapping: dict[str, tuple[str, str]] = {
            ".png": ("imagem", "image/png"),
            ".jpg": ("imagem", "image/jpeg"),
            ".jpeg": ("imagem", "image/jpeg"),
            ".gif": ("imagem", "image/gif"),
            ".webp": ("imagem", "image/webp"),
            ".bmp": ("imagem", "image/bmp"),
            ".tif": ("imagem", "image/tiff"),
            ".tiff": ("imagem", "image/tiff"),
            ".jp2": ("imagem", "image/jp2"),
            ".jpx": ("imagem", "image/jpx"),
            ".jpx2": ("imagem", "image/jpx"),
            ".json": ("documento", "application/json"),
            ".txt": ("documento", "text/plain"),
        }
        hit = mapping.get(ext.lower())
        if hit:
            return hit[0], hit[1]
        return parent.file_type, parent.mime_type

    def _build_display_filename(
        self,
        job: AnalysisJob,
        parent: Evidence,
        artifact_filename: str,
        label: Optional[str],
    ) -> str:
        if label:
            stem = label.strip()
        else:
            params = job.parameters or {}
            channel = params.get("channel_mode", "")
            parts = [job.technique]
            if channel:
                parts.append(str(channel))
            if job.technique == "ela" and "quality" in params:
                parts.append(f"q{params['quality']}")
            stem = "_".join(parts)
        ext = Path(artifact_filename).suffix or ".png"
        parent_stem = Path(parent.original_filename).stem
        return f"{stem}_{parent_stem}{ext}"

    def _load_evidence(self, evidence_id: uuid.UUID | str | None) -> Evidence | None:
        if not evidence_id:
            return None
        try:
            eid = evidence_id if isinstance(evidence_id, uuid.UUID) else uuid.UUID(str(evidence_id))
        except ValueError:
            return None
        return (
            self.db.query(Evidence)
            .filter(Evidence.id == eid, Evidence.deleted_at.is_(None))
            .first()
        )

    def _collect_similarity_matrix_parents(
        self, job: AnalysisJob, fallback: Evidence
    ) -> list[tuple[Evidence, str]]:
        """Insumos de jobs de matriz (todas evidencias questionadas + referencias)."""
        params = job.parameters or {}
        seen: set[str] = set()
        out: list[tuple[Evidence, str]] = []

        def add(evidence_id: object | None, role: str) -> None:
            ev = self._load_evidence(evidence_id)
            if not ev:
                return
            key = str(ev.id)
            if key in seen:
                return
            seen.add(key)
            out.append((ev, role))

        for eid in params.get("questioned_evidence_ids") or []:
            add(eid, "questioned")
        if params.get("mode") == "with_reference":
            for eid in params.get("reference_evidence_ids") or []:
                add(eid, "reference")

        if not out and fallback:
            out.append((fallback, "questioned"))
        return out

    @staticmethod
    def _similarity_matrix_metric_from_artifact(artifact_filename: str) -> str:
        lower = artifact_filename.lower()
        if "wl" in lower:
            return "wl_kernel"
        if "jaccard" in lower:
            return "jaccard"
        return "matrix"

    def _similarity_matrix_procedure_summary(
        self, job: AnalysisJob, job_result: dict[str, Any], metric: str
    ) -> str:
        params = job.parameters or {}
        mode = params.get("mode") or job_result.get("mode") or "all_pairs"
        q_count = int(job_result.get("questioned_count") or len(params.get("questioned_evidence_ids") or []))
        r_count = int(job_result.get("reference_count") or len(params.get("reference_evidence_ids") or []))
        technique_label = "ISO BMFF" if job.technique == "isomedia_compare" else "PDF estrutural"
        metric_label = "WL kernel" if metric == "wl_kernel" else "Jaccard" if metric == "jaccard" else metric
        if mode == "with_reference" and r_count > 0:
            size = f"{q_count}×{r_count}"
        else:
            size = f"{q_count}×{q_count}"
        return f"Matriz similaridade {technique_label} ({size}) · {metric_label}"

    @staticmethod
    def _jpeg_structure_artifact_role(artifact_filename: str) -> tuple[str, str]:
        lower = artifact_filename.lower()
        if "grid" in lower and lower.endswith(".json"):
            return "jpeg_structure_grid_json", "jpeg_structure_compare_grid_json_save"
        if "grid" in lower and lower.endswith(".txt"):
            return "jpeg_structure_grid_report", "jpeg_structure_compare_grid_txt_save"
        if lower.endswith(".json"):
            return "jpeg_structure_matrix_json", "jpeg_structure_compare_matrix_json_save"
        if lower.endswith(".png"):
            return "jpeg_structure_matrix_png", "jpeg_structure_compare_matrix_png_save"
        if lower.endswith(".txt"):
            return "jpeg_structure_matrix_report", "jpeg_structure_compare_report_txt_save"
        return "jpeg_structure_result", "jpeg_structure_compare_artifact_save"

    @staticmethod
    def _effective_derivation_technique(
        job: AnalysisJob, job_result: dict[str, Any] | None = None
    ) -> str:
        """Identificador da técnica na cadeia de custódia (ex.: trufor em vez de imdlbenco)."""
        if job.technique == "imdlbenco":
            params = job.parameters or {}
            method = params.get("method")
            if not method and job_result:
                method = job_result.get("method")
            if method:
                return str(method)
        return job.technique

    @staticmethod
    def _ml_localization_artifact_role(
        technique_id: str, artifact_filename: str
    ) -> tuple[str, str]:
        """Papel do artefato e passo de derivação para técnicas de localização DL."""
        lower = artifact_filename.lower()
        stem = Path(artifact_filename).stem.lower()
        if "confidence_map" in lower or stem == "confidence_map":
            suffix = "confidence_map"
        elif "noiseprint_map" in lower or stem == "noiseprint_map":
            suffix = "fingerprint_map"
        elif "valid_mask" in lower:
            suffix = "valid_mask"
        elif "valid_overlay" in lower:
            suffix = "valid_overlay"
        elif "multi_segment" in lower:
            suffix = "multi_segment"
        elif "heatmap" in lower:
            suffix = "heatmap"
        elif "overlay" in lower:
            suffix = "overlay"
        elif "mask" in lower:
            suffix = "mask"
        elif "input_image" in lower:
            suffix = "input_image"
        else:
            suffix = "artifact"
        artifact_role = f"{technique_id}_{suffix}"
        derivation_step = f"{technique_id}_{suffix}_save"
        return artifact_role, derivation_step

    def _jpeg_structure_procedure_summary(
        self, job: AnalysisJob, job_result: dict[str, Any], artifact_filename: str
    ) -> str:
        params = job.parameters or {}
        mode = params.get("mode") or job_result.get("mode") or "all_pairs"
        q_count = int(job_result.get("questioned_count") or len(params.get("questioned_evidence_ids") or []))
        r_count = int(job_result.get("reference_count") or len(params.get("reference_evidence_ids") or []))
        if mode == "with_reference" and r_count > 0:
            size = f"{r_count}×{q_count}"
        else:
            size = f"{q_count}×{q_count}"
        lower = artifact_filename.lower()
        is_grid = "grid" in lower
        kind = "JSON" if lower.endswith(".json") else ("PNG" if lower.endswith(".png") else "TXT")
        label = "Grade posicional JPEG" if is_grid else "Matriz similaridade JPEG estrutural"
        return f"{label} ({size}) · {kind}"

    def _prnu_parent_inputs(
        self, job: AnalysisJob, questioned: Evidence
    ) -> List[dict[str, Any]]:
        parents_ev: list[tuple[Evidence, str]] = [(questioned, "questioned")]
        fp_id = (job.parameters or {}).get("fingerprint_id")
        fingerprint = self._load_evidence(fp_id)
        if fingerprint:
            parents_ev.append((fingerprint, "fingerprint"))
        return [parent_ref_from_evidence(ev, role) for ev, role in parents_ev]

    def _resolve_job_parent_inputs(
        self,
        job: AnalysisJob,
        questioned: Evidence,
        artifact_filename: str,
        job_result: dict[str, Any] | None = None,
    ) -> Tuple[List[dict[str, Any]], str, str]:
        """Retorna (parent_inputs, derivation_step, artifact_role)."""
        if job.technique == "prnu":
            lower = artifact_filename.lower()
            if "correlation_surface" in lower:
                parent_inputs = self._prnu_parent_inputs(job, questioned)
                return parent_inputs, "correlation_surface_C", "prnu_correlation_surface"
            if "localized" in lower:
                parent_inputs = self._prnu_parent_inputs(job, questioned)
                if "overlay" in lower:
                    role = "prnu_localized_overlay"
                elif "positive" in lower:
                    role = "prnu_localized_positive"
                else:
                    role = "prnu_localized_map"
                return parent_inputs, "prnu_localized_maps_save", role

        if job.technique in ("isomedia_compare", "pdf_structure_similarity"):
            parents_ev = self._collect_similarity_matrix_parents(job, questioned)
            parent_inputs = [parent_ref_from_evidence(ev, role) for ev, role in parents_ev]
            metric = self._similarity_matrix_metric_from_artifact(artifact_filename)
            step = f"{job.technique}_{metric}_matrix_save"
            artifact_role = f"similarity_matrix_{metric}"
            return parent_inputs, step, artifact_role

        if job.technique == "jpeg_structure_compare":
            parents_ev = self._collect_similarity_matrix_parents(job, questioned)
            parent_inputs = [parent_ref_from_evidence(ev, role) for ev, role in parents_ev]
            artifact_role, step = self._jpeg_structure_artifact_role(artifact_filename)
            return parent_inputs, step, artifact_role

        if job.technique in ("synthetic_image_detection", "sepael"):
            parent_inputs = [parent_ref_from_evidence(questioned, "input")]
            lower = artifact_filename.lower()
            prefix = "synthetic_image_detection"
            if "model_scores" in lower:
                return parent_inputs, f"{prefix}_model_scores_save", f"{prefix}_model_scores"
            return parent_inputs, f"{prefix}_visual_save", f"{prefix}_visual"

        parent_inputs = [parent_ref_from_evidence(questioned, "input")]
        if job.technique == "metadata" or "metadata_report" in artifact_filename.lower():
            return parent_inputs, "metadata_report_save", "metadata_report"

        if job.technique == "videofact":
            lower = artifact_filename.lower()
            if lower.endswith(".json"):
                return parent_inputs, "videofact_report_save", "videofact_report"
            if lower.endswith(".txt"):
                return parent_inputs, "videofact_report_save", "videofact_summary"
            if "scores" in lower and lower.endswith(".png"):
                return parent_inputs, "videofact_chart_save", "videofact_scores_chart"

        if job.technique in ("imdlbenco", "safire", "noiseprint"):
            effective = self._effective_derivation_technique(job, job_result)
            artifact_role, step = self._ml_localization_artifact_role(effective, artifact_filename)
            return parent_inputs, step, artifact_role

        artifact_role = "heatmap" if "heatmap" in artifact_filename.lower() else "result"
        step = f"{job.technique}_artifact_save"
        return parent_inputs, step, artifact_role

    def _register_derivative_custody(
        self,
        *,
        case_id: uuid.UUID,
        derivative: Evidence,
        provenance: dict[str, Any],
        user_id: uuid.UUID,
        job_id: uuid.UUID | None = None,
        label: str | None = None,
        extra_details: dict[str, Any] | None = None,
    ) -> None:
        op = provenance["operation"]
        details = provenance_to_custody_details(provenance)
        if label:
            details["label"] = label
        if extra_details:
            details.update(extra_details)

        custody = CustodyService(self.db)
        custody.create_record(
            record_type="derivative_saved",
            case_id=case_id,
            evidence_id=derivative.id,
            job_id=job_id,
            user_id=user_id,
            sha256_input=compute_sha256_input(provenance["parent_inputs"]),
            sha256_output=derivative.sha256,
            sha256_params=compute_sha256_params(
                op,
                artifact_role=provenance["output"]["artifact_role"],
                artifact_filename=provenance["output"].get("artifact_filename"),
            ),
            details=details,
        )

    def save_from_job(
        self,
        job_id: uuid.UUID,
        artifact_filename: str,
        user_id: uuid.UUID,
        label: Optional[str] = None,
        effective_parameters: Optional[Dict[str, Any]] = None,
    ) -> Evidence:
        """Copy a completed job artifact into derivatives storage and register custody."""
        job = self.db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            raise DerivativeSaveError("Job nao encontrado")
        if job.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Job ainda nao completado",
            )

        parent = self._load_evidence(job.evidence_id)
        if not parent:
            raise DerivativeSaveError("Evidencia de origem nao encontrada")

        results_dir = Path(self.settings.RESULTS_DIR) / str(job.id)
        job_result = self._load_job_result_json(job.id)
        params = merge_effective_parameters(job, job_result, override=effective_parameters)

        try:
            materialize_preview_artifact(job.technique, results_dir, artifact_filename, params)
        except (FileNotFoundError, ValueError) as exc:
            raise DerivativeSaveError(str(exc)) from exc

        persist_effective_parameters(results_dir, params)
        sync_job_parameters(job, params)
        sync_job_runtime_receipt(job, results_dir, params)
        job_result = _load_result_json_from_dir(results_dir)

        artifact_path = results_dir / artifact_filename
        if not artifact_path.exists():
            raise DerivativeSaveError(f"Artefato '{artifact_filename}' nao encontrado no resultado do job")

        if not artifact_path.resolve().is_relative_to(results_dir.resolve()):
            raise DerivativeSaveError("Artefato invalido")

        derivatives_root = Path(self.settings.DERIVATIVES_DIR) / str(parent.case_id)
        derivatives_root.mkdir(parents=True, exist_ok=True)

        evidence_id = uuid.uuid4()
        ext = artifact_path.suffix or ".png"
        stored_filename = f"{evidence_id}{ext}"
        dest_path = derivatives_root / stored_filename
        shutil.copy2(str(artifact_path), str(dest_path))

        file_size = dest_path.stat().st_size
        output_sha256 = self._compute_sha256(dest_path)
        display_name = self._build_display_filename(job, parent, artifact_filename, label)

        procedure_summary = self._procedure_summary(job)

        out_file_type, out_mime = self._file_type_and_mime_for_derivative(ext, parent)

        provenance_technique = self._effective_derivation_technique(job, job_result)

        parent_inputs, derivation_step, artifact_role = self._resolve_job_parent_inputs(
            job, parent, artifact_filename, job_result=job_result
        )

        outputs_metrics = None
        if job.technique == "prnu" and "correlation_surface" in artifact_filename.lower():
            outputs_metrics = DerivationLineageBuilder.extract_prnu_job_outputs(job_result)
            mode = params.get("mode", "full")
            sigma = params.get("sigma")
            procedure_summary = f"PRNU correlacao · superficie C · modo {mode}"
            if sigma is not None:
                procedure_summary += f" · σ={sigma}"
            if outputs_metrics and outputs_metrics.get("pce") is not None:
                procedure_summary += f" · PCE={outputs_metrics['pce']}"
        elif job.technique in ("isomedia_compare", "pdf_structure_similarity"):
            metric = self._similarity_matrix_metric_from_artifact(artifact_filename)
            procedure_summary = self._similarity_matrix_procedure_summary(job, job_result, metric)
            mode = params.get("mode") or job_result.get("mode") or "all_pairs"
            q_count = int(job_result.get("questioned_count") or len(params.get("questioned_evidence_ids") or []))
            r_count = int(job_result.get("reference_count") or len(params.get("reference_evidence_ids") or []))
            outputs_metrics = {
                "mode": mode,
                "questioned_count": q_count,
                "reference_count": r_count,
                "matrix_metric": metric,
                "input_count": len(parent_inputs),
            }
        elif job.technique == "jpeg_structure_compare":
            procedure_summary = self._jpeg_structure_procedure_summary(job, job_result, artifact_filename)
            mode = params.get("mode") or job_result.get("mode") or "all_pairs"
            q_count = int(job_result.get("questioned_count") or len(params.get("questioned_evidence_ids") or []))
            r_count = int(job_result.get("reference_count") or len(params.get("reference_evidence_ids") or []))
            outputs_metrics = {
                "mode": mode,
                "questioned_count": q_count,
                "reference_count": r_count,
                "artifact_kind": artifact_filename.rsplit(".", 1)[-1].lower(),
                "input_count": len(parent_inputs),
                "criteria_version": job_result.get("criteria_version"),
            }
        elif job.technique in ("synthetic_image_detection", "sepael"):
            lower = artifact_filename.lower()
            if "model_scores" in lower:
                procedure_summary = "Detecção de imagens sintéticas — escores dos modelos"
            else:
                stem = Path(artifact_filename).stem.replace("_", " ")
                procedure_summary = f"Detecção de imagens sintéticas — visual ({stem})"
            outputs_metrics = {
                "inference_device": job_result.get("inference_device"),
                "mode": job_result.get("mode") or params.get("mode"),
                "generate_visuals": job_result.get("generate_visuals"),
            }
        elif job.technique == "prnu" and "localized" in artifact_filename.lower():
            procedure_summary = "PRNU mapas localizados"
            outputs_metrics = {
                "block_half": params.get("block_half"),
                "overlap_k": params.get("overlap_k"),
                "localized_threshold": params.get("localized_threshold"),
                "fingerprint_id": params.get("fingerprint_id"),
            }
        elif job.technique == "videofact":
            procedure_summary = f"VideoFACT — relatorio ({params.get('mode', 'both')})"
            outputs_metrics = {
                "mode": params.get("mode") or job_result.get("mode"),
                "inference_device": job_result.get("inference_device"),
            }
        elif job.technique in ("imdlbenco", "safire", "noiseprint"):
            stem = Path(artifact_filename).stem.replace("_", " ")
            procedure_summary = f"{provenance_technique.upper()} — {stem}"
            outputs_metrics: dict[str, Any] = {
                "inference_device": job_result.get("inference_device"),
            }
            if job.technique == "imdlbenco":
                outputs_metrics["method"] = provenance_technique
        else:
            procedure_summary = procedure_summary

        job_completed_at = None
        if job.completed_at:
            job_completed_at = job.completed_at.isoformat()

        job_receipt = load_job_execution_receipt(
            job_result,
            job.runtime_manifest if isinstance(job.runtime_manifest, dict) else None,
        )
        if job_receipt is None:
            raise DerivativeSaveError(
                "Recibo de execucao do job ausente. Reexecute a analise antes de salvar o derivado."
            )

        promoted_repro = build_promoted_reproducibility_record(
            technique=job.technique,
            job_receipt=job_receipt,
            artifact_path=artifact_path,
            artifact_filename=artifact_filename,
            result_dir=results_dir,
            result=job_result,
        )

        repro_sidecar = derivatives_root / f"{evidence_id}.reproducibility.json"
        with open(repro_sidecar, "w", encoding="utf-8") as f:
            json.dump(promoted_repro, f, ensure_ascii=False, indent=2)

        operation = build_operation(
            technique=provenance_technique,
            derivation_step=derivation_step,
            parameters=params,
            source_job_id=str(job.id),
            job_completed_at=job_completed_at,
            outputs_metrics=outputs_metrics,
            procedure_summary=procedure_summary,
            runtime=job_receipt.get("runtime"),
            artifact_sha256=promoted_repro["artifact_sha256"],
            determinism_profile=promoted_repro.get("determinism_profile"),
        )
        output_block = build_output(
            evidence_id=str(evidence_id),
            original_filename=display_name,
            sha256=output_sha256,
            artifact_role=artifact_role,
            artifact_filename=artifact_filename,
            file_type=out_file_type,
        )
        provenance = build_provenance_snapshot(
            parent_inputs=parent_inputs,
            operation=operation,
            output=output_block,
        )

        extra_metadata = build_derivation_metadata(
            parents=parent_inputs,
            technique=provenance_technique,
            derivation_step=derivation_step,
            procedure_summary=procedure_summary,
            parameters=params,
            artifact_role=artifact_role,
            artifact_filename=artifact_filename,
            derivation_outputs=outputs_metrics,
            source_job_id=str(job.id),
            label=label,
            provenance=provenance,
            extra={"reproducibility": promoted_repro},
        )

        derivative = Evidence(
            id=evidence_id,
            case_id=parent.case_id,
            filename=stored_filename,
            original_filename=display_name,
            file_path=str(dest_path),
            file_size=file_size,
            file_type=out_file_type,
            mime_type=out_mime,
            sha256=output_sha256,
            extra_metadata=extra_metadata,
            uploaded_by=user_id,
        )
        self.db.add(derivative)
        self.db.flush()

        self._register_derivative_custody(
            case_id=parent.case_id,
            derivative=derivative,
            provenance=provenance,
            user_id=user_id,
            job_id=job.id,
            label=label,
        )

        record_promoted_derivative(
            results_dir,
            evidence_id=str(derivative.id),
            artifact_filename=artifact_filename,
            sha256=output_sha256,
            label=label,
        )

        self.db.commit()
        self.db.refresh(derivative)

        from models.case import Case as CaseModel
        from services.peritus_va_materializer import mark_peritus_binding_modified

        case_row = self.db.query(CaseModel).filter(CaseModel.id == parent.case_id).first()
        if case_row and getattr(case_row, "storage_mode", "va") == "peritus":
            mark_peritus_binding_modified(self.settings, parent.case_id)

        return derivative

    def save_prnu_fingerprint(
        self,
        case_id: uuid.UUID,
        npy_source_path: Path,
        parent_evidence_ids: list[uuid.UUID],
        user_id: uuid.UUID,
        label: str,
        sigma: float,
        images_used: int,
        shape: list | None,
        reference_group_label: str | None = None,
    ) -> Evidence:
        """Persist a PRNU camera fingerprint (.npy) as derived evidence with custody."""
        if not parent_evidence_ids:
            raise DerivativeSaveError("Nenhuma evidencia de origem para o fingerprint")

        parents: list[Evidence] = []
        for pid in parent_evidence_ids:
            parent = self._load_evidence(pid)
            if not parent or parent.case_id != case_id:
                raise DerivativeSaveError(f"Evidencia de origem invalida: {pid}")
            parents.append(parent)

        if not npy_source_path.exists():
            raise DerivativeSaveError("Arquivo de fingerprint nao encontrado")

        derivatives_root = Path(self.settings.DERIVATIVES_DIR) / str(case_id)
        derivatives_root.mkdir(parents=True, exist_ok=True)

        evidence_id = uuid.uuid4()
        stored_filename = f"{evidence_id}.npy"
        dest_path = derivatives_root / stored_filename
        shutil.copy2(str(npy_source_path), str(dest_path))

        file_size = dest_path.stat().st_size
        output_sha256 = self._compute_sha256(dest_path)
        display_name = f"{label.strip() or evidence_id.hex[:8]}.npy"

        params = {
            "sigma": sigma,
            "images_used": images_used,
            "source_evidence_ids": [str(p.id) for p in parents],
        }
        procedure_summary = f"PRNU fingerprint · {label} · σ={sigma}"

        parent_inputs = [
            parent_ref_from_evidence(p, "reference_input", p.original_filename) for p in parents
        ]

        operation = build_operation(
            technique="prnu",
            derivation_step="fingerprint_aggregate",
            parameters=params,
            procedure_summary=procedure_summary,
            outputs_metrics={"images_used": images_used},
        )
        output_block = build_output(
            evidence_id=str(evidence_id),
            original_filename=display_name,
            sha256=output_sha256,
            artifact_role="prnu_fingerprint",
            artifact_filename=f"{evidence_id}.npy",
            file_type="imagem",
        )
        provenance = build_provenance_snapshot(
            parent_inputs=parent_inputs,
            operation=operation,
            output=output_block,
        )

        extra_metadata = build_derivation_metadata(
            parents=parent_inputs,
            technique="prnu",
            derivation_step="fingerprint_aggregate",
            procedure_summary=procedure_summary,
            parameters=params,
            artifact_role="prnu_fingerprint",
            label=label,
            provenance=provenance,
            extra={
                "reference_group_label": reference_group_label,
                "sigma": sigma,
                "images_used": images_used,
                "shape": shape,
            },
        )

        derivative = Evidence(
            id=evidence_id,
            case_id=case_id,
            filename=stored_filename,
            original_filename=display_name,
            file_path=str(dest_path),
            file_size=file_size,
            file_type="imagem",
            mime_type="application/octet-stream",
            sha256=output_sha256,
            extra_metadata=extra_metadata,
            uploaded_by=user_id,
        )
        self.db.add(derivative)
        self.db.flush()

        self._register_derivative_custody(
            case_id=case_id,
            derivative=derivative,
            provenance=provenance,
            user_id=user_id,
            extra_details={"prnu_action": "fingerprint_generated", "images_used": images_used},
        )

        self.db.commit()
        self.db.refresh(derivative)
        return derivative

    def _load_job_result_json(self, job_id: uuid.UUID) -> Dict[str, Any]:
        path = Path(self.settings.RESULTS_DIR) / str(job_id) / "result.json"
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def get_lineage(self, evidence_id: uuid.UUID) -> dict:
        """Grafo de derivacao via DerivationLineageBuilder (papel + insumos)."""
        target = self._load_evidence(evidence_id)
        if not target:
            raise DerivativeSaveError("Evidencia nao encontrada")

        return DerivationLineageBuilder(self.db).build(target)
