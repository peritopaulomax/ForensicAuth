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
    if label:
        meta["label"] = label
    if extra:
        meta.update(extra)
    return meta
