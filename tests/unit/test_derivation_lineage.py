"""Grafos de derivacao genericos (DAG + operacoes)."""

import uuid
from unittest.mock import MagicMock

import pytest

from services.derivation_contract import PROVENANCE_SCHEMA_VERSION, build_derivation_metadata, parent_ref
from services.derivation_lineage import DerivationLineageBuilder


def _evidence(
    eid: uuid.UUID,
    filename: str,
    *,
    origin: str = "upload",
    extra: dict | None = None,
) -> MagicMock:
    meta = {"origin": origin, **(extra or {})}
    ev = MagicMock()
    ev.id = eid
    ev.case_id = uuid.uuid4()
    ev.original_filename = filename
    ev.file_type = "imagem"
    ev.sha256 = "a" * 64
    ev.extra_metadata = meta
    ev.deleted_at = None
    return ev


class TestDerivationContract:
    def test_build_metadata_parent_inputs(self):
        meta = build_derivation_metadata(
            parents=[
                parent_ref(
                    "id1",
                    "questioned",
                    sha256="a" * 64,
                    original_filename="q.jpg",
                    origin="upload",
                ),
                parent_ref(
                    "id2",
                    "fingerprint",
                    sha256="b" * 64,
                    original_filename="fp.npy",
                    origin="derived",
                ),
            ],
            technique="prnu",
            derivation_step="correlation_surface_C",
            procedure_summary="Correlacao",
            artifact_role="prnu_correlation_surface",
        )
        assert len(meta["parent_evidence_ids"]) == 2
        assert meta["parent_roles"]["questioned"] == "id1"
        assert meta["derivation_step"] == "correlation_surface_C"
        assert meta["provenance_schema_version"] == PROVENANCE_SCHEMA_VERSION


class TestDerivationLineageBuilder:
    def test_fingerprint_multi_parent_operation(self):
        ref1, ref2, fp_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        refs = [_evidence(ref1, "r1.jpg"), _evidence(ref2, "r2.jpg")]
        fp = _evidence(
            fp_id,
            "PRNU-D70-001.npy",
            origin="derived",
            extra={
                "artifact_role": "prnu_fingerprint",
                "parent_evidence_ids": [str(ref1), str(ref2)],
                "parent_inputs": [
                    {"evidence_id": str(ref1), "role": "reference_input"},
                    {"evidence_id": str(ref2), "role": "reference_input"},
                ],
                "derivation_step": "fingerprint_aggregate",
                "technique": "prnu",
                "procedure_summary": "PRNU fingerprint",
            },
        )
        store = {ref1: refs[0], ref2: refs[1], fp_id: fp}
        builder = DerivationLineageBuilder(MagicMock())
        builder._load_evidence = lambda eid: store.get(
            eid if isinstance(eid, uuid.UUID) else uuid.UUID(str(eid))
        )
        graph = builder.build(fp)
        assert graph["layout"] == "dag"
        assert graph["parent_count"] == 2
        assert len([e for e in graph["edges"] if e["to_evidence_id"] == str(fp_id)]) == 2
        assert all(n.get("layer") is not None for n in graph["nodes"])
        node_ids = {n["evidence_id"] for n in graph["nodes"]}
        assert str(ref1) in node_ids
        assert str(ref2) in node_ids
        fp_op = next((o for o in graph["operations"] if o["to_evidence_id"] == str(fp_id)), None)
        assert fp_op is not None
        assert fp_op["input_count"] == 2

    def test_correlation_dag_has_merge_operation(self):
        q_id, fp_id, surf_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        questioned = _evidence(q_id, "q.jpg")
        fingerprint = _evidence(
            fp_id,
            "fp.npy",
            origin="derived",
            extra={
                "artifact_role": "prnu_fingerprint",
                "parent_evidence_ids": [str(uuid.uuid4())],
                "parent_inputs": [{"evidence_id": str(uuid.uuid4()), "role": "reference_input"}],
                "derivation_step": "fingerprint_aggregate",
                "technique": "prnu",
            },
        )
        surface = _evidence(
            surf_id,
            "surf.html",
            origin="derived",
            extra={
                "artifact_role": "prnu_correlation_surface",
                "derivation_step": "correlation_surface_C",
                "technique": "prnu",
                "parent_inputs": [
                    {"evidence_id": str(q_id), "role": "questioned"},
                    {"evidence_id": str(fp_id), "role": "fingerprint"},
                ],
                "parent_evidence_ids": [str(q_id), str(fp_id)],
                "derivation_outputs": {"pce": 42.0, "mode": "full"},
                "procedure_summary": "Superficie C",
            },
        )
        ref_id = uuid.UUID(fingerprint.extra_metadata["parent_evidence_ids"][0])
        ref = _evidence(ref_id, "ref.jpg")
        store = {q_id: questioned, fp_id: fingerprint, surf_id: surface, ref_id: ref}
        builder = DerivationLineageBuilder(MagicMock())
        builder._load_evidence = lambda eid: store.get(
            eid if isinstance(eid, uuid.UUID) else uuid.UUID(str(eid))
        )
        graph = builder.build(surface)
        assert graph["layout"] == "dag"
        assert len(graph["operations"]) >= 1
        merge = next((o for o in graph["operations"] if o["to_evidence_id"] == str(surf_id)), None)
        assert merge is not None
        assert len(merge["inputs"]) == 2
        roles = {inp["role"] for inp in merge["inputs"]}
        assert "questioned" in roles
        assert "fingerprint" in roles
        node_ids = {n["evidence_id"] for n in graph["nodes"]}
        assert str(q_id) in node_ids
        assert str(fp_id) in node_ids
        assert str(ref_id) in node_ids
        assert str(surf_id) in node_ids

    def test_single_parent_original_in_nodes(self):
        orig_id, deriv_id = uuid.uuid4(), uuid.uuid4()
        original = _evidence(orig_id, "evidencia.jpg")
        derived = _evidence(
            deriv_id,
            "ela_heatmap.png",
            origin="derived",
            extra={
                "technique": "ela",
                "parent_evidence_id": str(orig_id),
                "procedure_summary": "ELA RGB Q95",
            },
        )
        store = {orig_id: original, deriv_id: derived}
        builder = DerivationLineageBuilder(MagicMock())
        builder._load_evidence = lambda eid: store.get(
            eid if isinstance(eid, uuid.UUID) else uuid.UUID(str(eid))
        )
        graph = builder.build(derived)
        node_ids = {n["evidence_id"] for n in graph["nodes"]}
        assert str(orig_id) in node_ids
        assert str(deriv_id) in node_ids
        orig_node = next(n for n in graph["nodes"] if n["evidence_id"] == str(orig_id))
        deriv_node = next(n for n in graph["nodes"] if n["evidence_id"] == str(deriv_id))
        assert orig_node["layer"] < deriv_node["layer"]
