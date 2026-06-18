"""Provenance schema v1 — contrato, hashes e autossuficiencia na cadeia."""

import uuid
from unittest.mock import MagicMock

import pytest

from services.derivation_contract import (
    PROVENANCE_SCHEMA_VERSION,
    build_derivation_metadata,
    build_operation,
    build_output,
    build_provenance_snapshot,
    compute_sha256_input,
    compute_sha256_params,
    parent_ref_from_evidence,
    provenance_to_custody_details,
)


def _evidence(filename: str, sha: str | None = None) -> MagicMock:
    eid = uuid.uuid4()
    ev = MagicMock()
    ev.id = eid
    ev.original_filename = filename
    ev.file_type = "imagem"
    ev.sha256 = sha or ("a" * 64)
    ev.extra_metadata = {"origin": "upload"}
    return ev


class TestProvenanceContract:
    def test_parent_ref_from_evidence_includes_sha256(self):
        ev = _evidence("3.jpg")
        ref = parent_ref_from_evidence(ev, "questioned", "Evidencia questionada")
        assert ref["sha256"] == ev.sha256
        assert ref["original_filename"] == "3.jpg"
        assert ref["evidence_id"] == str(ev.id)
        assert ref["role"] == "questioned"

    def test_compute_sha256_input_single_parent(self):
        ref = parent_ref_from_evidence(_evidence("a.jpg"), "input")
        assert compute_sha256_input([ref]) == ref["sha256"]

    def test_compute_sha256_input_multi_parent_canonical(self):
        r1 = parent_ref_from_evidence(_evidence("r1.jpg"), "reference_input")
        r2 = parent_ref_from_evidence(_evidence("r2.jpg"), "reference_input")
        h = compute_sha256_input([r2, r1])
        h2 = compute_sha256_input([r1, r2])
        assert h == h2

    def test_provenance_snapshot_in_custody_details(self):
        q = parent_ref_from_evidence(_evidence("3.jpg"), "questioned")
        fp = parent_ref_from_evidence(_evidence("fp.npy", "b" * 64), "fingerprint")
        op = build_operation(
            technique="prnu",
            derivation_step="correlation_surface_C",
            parameters={"mode": "full", "sigma": 2},
            source_job_id=str(uuid.uuid4()),
            outputs_metrics={"pce": 99.0},
            procedure_summary="Superficie C",
        )
        out = build_output(
            evidence_id=str(uuid.uuid4()),
            original_filename="surf.html",
            sha256="c" * 64,
            artifact_role="prnu_correlation_surface",
            artifact_filename="correlation_surface.html",
        )
        prov = build_provenance_snapshot(parent_inputs=[q, fp], operation=op, output=out)
        details = provenance_to_custody_details(prov)
        assert details["provenance_schema_version"] == PROVENANCE_SCHEMA_VERSION
        assert len(details["parent_inputs"]) == 2
        assert all(p.get("sha256") for p in details["parent_inputs"])
        assert details["parent_roles"]["questioned"] == q["evidence_id"]
        assert details["derivation_outputs"]["pce"] == 99.0

    def test_build_derivation_metadata_embeds_provenance(self):
        q = parent_ref_from_evidence(_evidence("q.jpg"), "questioned")
        meta = build_derivation_metadata(
            parents=[q],
            technique="ela",
            derivation_step="ela_artifact_save",
            procedure_summary="ELA",
            provenance=build_provenance_snapshot(
                parent_inputs=[q],
                operation=build_operation(technique="ela", derivation_step="ela_artifact_save"),
                output=build_output(
                    evidence_id=str(uuid.uuid4()),
                    original_filename="out.png",
                    sha256="d" * 64,
                    artifact_role="heatmap",
                ),
            ),
        )
        assert meta["provenance_schema_version"] == PROVENANCE_SCHEMA_VERSION
        assert meta["provenance"]["parent_inputs"][0]["sha256"] == q["sha256"]

    def test_sha256_params_includes_algorithm(self):
        op = build_operation(technique="ela", derivation_step="ela_artifact_save", parameters={"q": 95})
        h = compute_sha256_params(op, artifact_role="heatmap")
        assert len(h) == 64
