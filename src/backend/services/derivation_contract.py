"""Contrato de proveniencia v1 — insumos, operacao, saida (cadeia + extra_metadata)."""

from __future__ import annotations

from typing import Any

from services.custody_utils import hash_canonical_json

PROVENANCE_SCHEMA_VERSION = "1"
DEFAULT_PLUGIN_ID = "forensic_plugin"


def evidence_origin(extra_metadata: dict[str, Any] | None) -> str:
    meta = extra_metadata or {}
    if meta.get("origin") == "derived":
        return "derived"
    if meta.get("evidence_class") == "reference":
        return "reference"
    return "upload"


def parent_ref_from_evidence(
    evidence: Any,
    role: str,
    label: str | None = None,
) -> dict[str, Any]:
    """Insumo com identidade + hash de bytes (autossuficiente na cadeia)."""
    meta = evidence.extra_metadata or {}
    return {
        "evidence_id": str(evidence.id),
        "role": role,
        "label": label or evidence.original_filename,
        "original_filename": evidence.original_filename,
        "sha256": evidence.sha256,
        "file_type": evidence.file_type,
        "origin": evidence_origin(meta),
    }


def parent_ref(
    evidence_id: str,
    role: str,
    label: str | None = None,
    *,
    original_filename: str | None = None,
    sha256: str | None = None,
    file_type: str | None = None,
    origin: str | None = None,
) -> dict[str, Any]:
    """Referencia de insumo; sha256/origin obrigatorios em gravacoes novas."""
    ref: dict[str, Any] = {
        "evidence_id": evidence_id,
        "role": role,
        "label": label,
    }
    if original_filename is not None:
        ref["original_filename"] = original_filename
    if sha256 is not None:
        ref["sha256"] = sha256
    if file_type is not None:
        ref["file_type"] = file_type
    if origin is not None:
        ref["origin"] = origin
    return ref


def build_operation(
    *,
    technique: str,
    derivation_step: str,
    parameters: dict[str, Any] | None = None,
    source_job_id: str | None = None,
    job_completed_at: str | None = None,
    outputs_metrics: dict[str, Any] | None = None,
    procedure_summary: str = "",
    plugin_id: str = DEFAULT_PLUGIN_ID,
    plugin_version: str = "1",
    runtime: dict[str, Any] | None = None,
    artifact_sha256: str | None = None,
    determinism_profile: str | None = None,
) -> dict[str, Any]:
    op: dict[str, Any] = {
        "technique": technique,
        "derivation_step": derivation_step,
        "procedure_summary": procedure_summary,
        "parameters": parameters or {},
        "algorithm": {"plugin": plugin_id, "version": plugin_version},
    }
    if source_job_id:
        op["source_job_id"] = source_job_id
    if job_completed_at:
        op["job_completed_at"] = job_completed_at
    if outputs_metrics:
        op["outputs_metrics"] = outputs_metrics
    if runtime:
        op["runtime"] = runtime
    if artifact_sha256:
        op["artifact_sha256"] = artifact_sha256
    if determinism_profile:
        op["determinism_profile"] = determinism_profile
    return op


def build_output(
    *,
    evidence_id: str,
    original_filename: str,
    sha256: str,
    artifact_role: str,
    artifact_filename: str | None = None,
    file_type: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "evidence_id": evidence_id,
        "original_filename": original_filename,
        "sha256": sha256,
        "artifact_role": artifact_role,
    }
    if artifact_filename:
        out["artifact_filename"] = artifact_filename
    if file_type:
        out["file_type"] = file_type
    return out


def build_provenance_snapshot(
    *,
    parent_inputs: list[dict[str, Any]],
    operation: dict[str, Any],
    output: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
        "parent_inputs": parent_inputs,
        "operation": operation,
        "output": output,
    }


def compute_sha256_input(parent_inputs: list[dict[str, Any]]) -> str:
    if not parent_inputs:
        return ""
    refs = []
    for p in parent_inputs:
        if not p.get("sha256"):
            continue
        refs.append(
            {
                "evidence_id": p.get("evidence_id"),
                "sha256": p["sha256"],
                "role": p.get("role"),
            }
        )
    if not refs:
        return ""
    refs.sort(key=lambda x: str(x.get("evidence_id") or ""))
    if len(refs) == 1:
        return refs[0]["sha256"]
    return hash_canonical_json({"parent_inputs": refs})


def compute_sha256_params(
    operation: dict[str, Any],
    *,
    artifact_role: str,
    artifact_filename: str | None = None,
) -> str:
    algo = operation.get("algorithm") or {}
    payload = {
        "technique": operation.get("technique"),
        "derivation_step": operation.get("derivation_step"),
        "parameters": operation.get("parameters") or {},
        "algorithm": algo,
        "artifact_role": artifact_role,
        "outputs_metrics": operation.get("outputs_metrics"),
    }
    runtime = operation.get("runtime") or {}
    digest = runtime.get("docker_image_digest")
    if digest:
        payload["runtime_digest"] = digest
    if operation.get("artifact_sha256"):
        payload["source_artifact_sha256"] = operation.get("artifact_sha256")
    if artifact_filename:
        payload["artifact_filename"] = artifact_filename
    return hash_canonical_json(payload)


def provenance_to_custody_details(provenance: dict[str, Any]) -> dict[str, Any]:
    """Detalhes imutaveis do registro derivative_saved (entram no record_hash)."""
    op = provenance.get("operation") or {}
    out = provenance.get("output") or {}
    parents = provenance.get("parent_inputs") or []
    first_parent = parents[0] if parents else {}
    return {
        "provenance_schema_version": provenance.get(
            "provenance_schema_version", PROVENANCE_SCHEMA_VERSION
        ),
        "parent_inputs": parents,
        "operation": op,
        "output": out,
        "technique": op.get("technique"),
        "derivation_step": op.get("derivation_step"),
        "procedure_summary": op.get("procedure_summary"),
        "parameters": op.get("parameters"),
        "source_job_id": op.get("source_job_id"),
        "derivation_outputs": op.get("outputs_metrics"),
        "artifact_role": out.get("artifact_role"),
        "artifact_filename": out.get("artifact_filename"),
        "derivative_filename": out.get("original_filename"),
        "parent_evidence_id": first_parent.get("evidence_id"),
        "parent_evidence_ids": [p.get("evidence_id") for p in parents if p.get("evidence_id")],
        "parent_roles": {
            p["role"]: p["evidence_id"] for p in parents if p.get("role") and p.get("evidence_id")
        },
    }


def build_derivation_metadata(
    *,
    parents: list[dict[str, Any]],
    technique: str,
    derivation_step: str,
    procedure_summary: str,
    parameters: dict[str, Any] | None = None,
    artifact_role: str = "result",
    artifact_filename: str | None = None,
    derivation_outputs: dict[str, Any] | None = None,
    source_job_id: str | None = None,
    derivation_group_id: str | None = None,
    label: str | None = None,
    extra: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
    output_evidence_id: str | None = None,
    output_sha256: str | None = None,
    output_filename: str | None = None,
) -> dict[str, Any]:
    """Metadados da evidencia derivada + bloco de proveniencia v1."""
    parent_ids = [p["evidence_id"] for p in parents if p.get("evidence_id")]
    parent_roles = {p["role"]: p["evidence_id"] for p in parents if p.get("role") and p.get("evidence_id")}

    outputs_metrics = derivation_outputs
    if provenance is None and output_evidence_id and output_sha256 and output_filename:
        operation = build_operation(
            technique=technique,
            derivation_step=derivation_step,
            parameters=parameters,
            source_job_id=source_job_id,
            outputs_metrics=outputs_metrics,
            procedure_summary=procedure_summary,
        )
        provenance = build_provenance_snapshot(
            parent_inputs=parents,
            operation=operation,
            output=build_output(
                evidence_id=output_evidence_id,
                original_filename=output_filename,
                sha256=output_sha256,
                artifact_role=artifact_role,
                artifact_filename=artifact_filename,
            ),
        )
    elif provenance is None:
        operation = build_operation(
            technique=technique,
            derivation_step=derivation_step,
            parameters=parameters,
            source_job_id=source_job_id,
            outputs_metrics=outputs_metrics,
            procedure_summary=procedure_summary,
        )
        provenance = build_provenance_snapshot(
            parent_inputs=parents,
            operation=operation,
            output=build_output(
                evidence_id=output_evidence_id or "",
                original_filename=output_filename or "",
                sha256=output_sha256 or "",
                artifact_role=artifact_role,
                artifact_filename=artifact_filename,
            ),
        )

    meta: dict[str, Any] = {
        "origin": "derived",
        "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
        "provenance": provenance,
        "parent_evidence_id": parent_ids[0] if parent_ids else None,
        "parent_evidence_ids": parent_ids,
        "parent_roles": parent_roles,
        "parent_inputs": parents,
        "technique": technique,
        "derivation_step": derivation_step,
        "procedure_summary": procedure_summary,
        "parameters": parameters or {},
        "artifact_role": artifact_role,
    }
    if artifact_filename:
        meta["artifact_filename"] = artifact_filename
    if derivation_outputs:
        meta["derivation_outputs"] = derivation_outputs
    if source_job_id:
        meta["source_job_id"] = source_job_id
    if derivation_group_id:
        meta["derivation_group_id"] = derivation_group_id
    if label:
        meta["label"] = label
    if extra:
        meta.update(extra)
    return meta


def reference_population_digest(selection: dict[str, Any] | list[Any] | None) -> str | None:
    """Hash canonico da selecao de populacao LR (insumo conceitual no grafo)."""
    if not selection:
        return None

    def _item_payload(item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        return {
            "base_group": item.get("base_group"),
            "subgroup": item.get("subgroup"),
            "key": item.get("key"),
        }

    if isinstance(selection, dict):
        fit_items = selection.get("fit_items")
        test_items = selection.get("test_items")
        if isinstance(fit_items, list) or isinstance(test_items, list):
            payload = {
                "fit_items": sorted(
                    [p for p in (_item_payload(item) for item in (fit_items or [])) if p],
                    key=lambda x: (str(x.get("base_group")), str(x.get("subgroup")), str(x.get("key"))),
                ),
                "test_items": sorted(
                    [p for p in (_item_payload(item) for item in (test_items or [])) if p],
                    key=lambda x: (str(x.get("base_group")), str(x.get("subgroup")), str(x.get("key"))),
                ),
            }
            if not payload["fit_items"] and not payload["test_items"]:
                return None
            return hash_canonical_json({"reference_population": payload})

        items = selection.get("items")
        if not isinstance(items, list):
            return None
        payload = [
            p for p in (_item_payload(item) for item in items) if p
        ]
    elif isinstance(selection, list):
        payload = [p for p in (_item_payload(item) for item in selection) if p]
    else:
        return None
    if not payload:
        return None
    payload.sort(key=lambda x: (str(x.get("base_group")), str(x.get("subgroup")), str(x.get("key"))))
    return hash_canonical_json({"reference_population": payload})


# Matriz de contrato: insumos, parametros minimos e artefatos promoviveis por tecnica.
TECHNIQUE_PROVENANCE_CONTRACT: dict[str, dict[str, Any]] = {
    "ela": {
        "parent_roles": ["input"],
        "min_parameters": ["quality", "channel_mode", "gain"],
        "savable_artifacts": ["heatmap.png"],
    },
    "dct_quantization": {
        "parent_roles": ["questioned", "reference"],
        "parent_roles_by_mode": {"reference": ["questioned", "reference"], "estimate": ["questioned"]},
        "min_parameters": ["mode"],
        "savable_artifacts": ["artifacts_upscaled.png", "estimated_matrix.png", "jpegio_matrix.png"],
    },
    "metadata": {
        "parent_roles": ["input"],
        "min_parameters": [],
        "savable_artifacts": ["metadata_report.json", "metadata_report.txt"],
    },
    "prnu": {
        "parent_roles": ["questioned", "fingerprint", "reference_input"],
        "min_parameters": ["mode"],
        "savable_artifacts": [
            "correlation_surface.html",
            "localized_map.png",
            "localized_overlay.png",
            "localized_positive.png",
        ],
    },
    "jpeg_structure_compare": {
        "parent_roles": ["questioned", "reference"],
        "min_parameters": ["mode", "questioned_evidence_ids"],
        "savable_artifacts": [
            "jpeg_structure_matrix.json",
            "jpeg_structure_matrix.png",
            "jpeg_structure_grid.json",
        ],
    },
    "pdf_structure_similarity": {
        "parent_roles": ["questioned", "reference"],
        "min_parameters": ["mode", "questioned_evidence_ids"],
        "savable_artifacts": ["similarity_matrices.json", "similarity_jaccard.png", "similarity_wl_kernel.png"],
    },
    "isomedia_compare": {
        "parent_roles": ["questioned", "reference"],
        "min_parameters": ["mode", "questioned_evidence_ids"],
        "savable_artifacts": ["similarity_matrices.json", "similarity_jaccard.png", "similarity_wl_kernel.png"],
    },
    "synthetic_image_detection": {
        "parent_roles": ["input", "lr_reference_population"],
        "min_parameters": ["selected_analyses", "reference_population", "meta_classifier"],
        "savable_artifacts": [
            "model_scores.txt",
            "lr_reference_summary.txt",
            "lr_reference_tippett.png",
            "nlm_residue.png",
            "median_residue.png",
        ],
        "conceptual_inputs": ["lr_reference_population"],
    },
    "audio_spoofing_detection": {
        "parent_roles": ["input"],
        "min_parameters": ["window_seconds", "selected_analyses"],
        "savable_artifacts": [
            "audio_spoofing_details.json",
            "audio_spoofing_plot.json",
            "detector_scores.txt",
        ],
    },
    "stil_video_detection": {
        "parent_roles": ["input"],
        "min_parameters": ["sample_every", "max_frames"],
        "savable_artifacts": ["stil_report.json", "stil_scores_chart.png", "stil_summary.txt"],
    },
    "lowres_fake_video": {
        "parent_roles": ["input"],
        "min_parameters": ["sample_every", "max_frames"],
        "savable_artifacts": ["lfv_report.json", "lfv_scores_chart.png", "lfv_summary.txt"],
    },
    "videofact": {
        "parent_roles": ["input"],
        "min_parameters": ["mode"],
        "savable_artifacts": ["videofact_report.json", "videofact_summary.txt", "videofact_xfer_scores.png"],
    },
}


def provenance_contract_for_technique(technique: str) -> dict[str, Any] | None:
    return TECHNIQUE_PROVENANCE_CONTRACT.get(technique)
