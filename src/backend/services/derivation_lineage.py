"""Grafo de derivacao generico: percorre metadados/cadeia e produz DAG com camadas e operacoes."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from models.analysis_job import AnalysisJob
from models.evidence import Evidence


class DerivationLineageBuilder:
    """Monta lineage DAG a partir de parent_inputs / parent_evidence_ids e derivacao_step."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    @staticmethod
    def evidence_to_node(ev: Evidence, layer: int | None = None) -> dict[str, Any]:
        meta = ev.extra_metadata or {}
        is_derived = meta.get("origin") == "derived"
        node: dict[str, Any] = {
            "evidence_id": str(ev.id),
            "original_filename": ev.original_filename,
            "file_type": ev.file_type,
            "sha256": ev.sha256,
            "is_derived": is_derived,
            "is_synthetic": bool(meta.get("is_synthetic")),
            "synthetic_kind": meta.get("synthetic_kind"),
            "technique": meta.get("technique") if is_derived else None,
            "parameters": meta.get("parameters") if is_derived else None,
            "procedure_summary": meta.get("procedure_summary") if is_derived else None,
            "artifact_role": meta.get("artifact_role"),
            "derivation_step": meta.get("derivation_step"),
            "source_job_id": meta.get("source_job_id"),
            "derivation_group_id": meta.get("derivation_group_id"),
            "legacy_provenance": bool(meta.get("legacy_provenance")),
        }
        if layer is not None:
            node["layer"] = layer
        if meta.get("derivation_outputs"):
            node["derivation_outputs"] = meta["derivation_outputs"]
        images_used = meta.get("images_used")
        if images_used is None and isinstance(meta.get("parameters"), dict):
            images_used = meta["parameters"].get("images_used")
        if images_used is not None:
            node["images_used"] = images_used
        return node

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

    def _load_job(self, job_id: str | None) -> AnalysisJob | None:
        if not job_id:
            return None
        try:
            jid = uuid.UUID(str(job_id))
        except ValueError:
            return None
        return self.db.query(AnalysisJob).filter(AnalysisJob.id == jid).first()

    def _load_job_result(self, job_id: uuid.UUID) -> dict[str, Any]:
        from services.job_service import build_job_result_dir

        job = self._load_job(job_id)
        if not job or not job.evidence:
            return {}
        path = build_job_result_dir(
            self.settings.RESULTS_DIR,
            job.evidence.case_id,
            job.evidence_id,
            job.id,
        ) / "result.json"
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def build(self, target: Evidence) -> dict[str, Any]:
        nodes_map: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        edge_keys: set[tuple[str, str, str]] = set()
        expanded: set[str] = set()

        self._walk_upstream(target, nodes_map, edges, edge_keys, expanded)
        self._inject_lr_reference_node(target, nodes_map, edges, edge_keys)

        nodes = list(nodes_map.values())
        self._assign_layers(nodes, edges)
        operations = self._build_operations(nodes, edges)
        phases = self._build_phases(nodes, operations)
        derivation_groups = self._collect_derivation_groups(target)
        legacy_notes = self._collect_legacy_notes(nodes)

        layout_label = target.extra_metadata.get("procedure_summary") if target.extra_metadata else None
        if not layout_label:
            layout_label = target.original_filename
        if legacy_notes:
            layout_label = f"{layout_label} · {len(legacy_notes)} aviso(s) legado(s)"

        return {
            "target_id": str(target.id),
            "case_id": str(target.case_id),
            "layout": "dag",
            "layout_label": layout_label,
            "parent_count": sum(1 for e in edges if e["to_evidence_id"] == str(target.id)),
            "nodes": nodes,
            "edges": edges,
            "operations": operations,
            "phases": phases,
            "derivation_groups": derivation_groups,
            "legacy_notes": legacy_notes,
        }

    def _walk_upstream(
        self,
        child: Evidence,
        nodes_map: dict[str, dict[str, Any]],
        edges: list[dict[str, Any]],
        edge_keys: set[tuple[str, str, str]],
        expanded: set[str],
    ) -> None:
        """Percorre ancestrais; registra todo insumo (derivado ou original) em nodes_map."""
        cid = str(child.id)
        nodes_map.setdefault(cid, self.evidence_to_node(child))
        meta = child.extra_metadata or {}
        if self._needs_legacy_provenance_upgrade(child, meta):
            upgraded = dict(nodes_map[cid])
            upgraded["legacy_provenance"] = True
            nodes_map[cid] = upgraded

        for parent, role in self._resolve_all_parents(child, meta):
            pid = str(parent.id)
            nodes_map.setdefault(pid, self.evidence_to_node(parent))
            edge = self._edge_for_parent_child(parent, child, meta, role)
            key = (edge["from_evidence_id"], edge["to_evidence_id"], str(role))
            if key not in edge_keys:
                edge_keys.add(key)
                edges.append(edge)
            is_derived = bool(parent.extra_metadata and parent.extra_metadata.get("origin") == "derived")
            if is_derived and pid not in expanded:
                self._walk_upstream(parent, nodes_map, edges, edge_keys, expanded)

        expanded.add(cid)

    def _resolve_all_parents(self, child: Evidence, meta: dict[str, Any]) -> list[tuple[Evidence, str]]:
        parent_inputs = meta.get("parent_inputs")
        if isinstance(parent_inputs, list) and parent_inputs:
            out: list[tuple[Evidence, str]] = []
            for pin in parent_inputs:
                if not isinstance(pin, dict):
                    continue
                ev = self._load_evidence(pin.get("evidence_id"))
                if ev:
                    out.append((ev, str(pin.get("role") or "input")))
            if out:
                return out

        roles = meta.get("parent_roles") or {}
        ids = meta.get("parent_evidence_ids") or []
        if isinstance(ids, list) and ids:
            out = []
            for idx, pid in enumerate(ids):
                ev = self._load_evidence(pid)
                if not ev:
                    continue
                role = None
                for rname, rid in roles.items():
                    if str(rid) == str(pid):
                        role = str(rname)
                        break
                if role is None:
                    role = self._default_role_for_index(meta, idx)
                out.append((ev, role))
            if out:
                return out

        if self._is_legacy_prnu_surface(child, meta):
            questioned, fingerprint = self._resolve_correlation_parents(child, meta)
            out = []
            if questioned:
                out.append((questioned, "questioned"))
            if fingerprint:
                out.append((fingerprint, "fingerprint"))
            return out

        pid = meta.get("parent_evidence_id")
        if pid:
            ev = self._load_evidence(pid)
            if ev:
                return [(ev, "input")]
        return []

    @staticmethod
    def _default_role_for_index(meta: dict[str, Any], idx: int) -> str:
        role = meta.get("artifact_role")
        if role == "prnu_correlation_surface":
            return "questioned" if idx == 0 else "fingerprint"
        if role == "prnu_fingerprint":
            return "reference_input"
        return f"input_{idx}"

    @staticmethod
    def _is_legacy_prnu_surface(_target: Evidence, meta: dict[str, Any]) -> bool:
        if meta.get("artifact_role") == "prnu_correlation_surface":
            return False
        if meta.get("technique") != "prnu":
            return False
        label = (meta.get("label") or "").lower()
        artifact = (meta.get("artifact_filename") or "").lower()
        return "superficie" in label or "correlation_surface" in artifact

    def _resolve_correlation_parents(
        self, target: Evidence, meta: dict[str, Any]
    ) -> tuple[Evidence | None, Evidence | None]:
        roles = meta.get("parent_roles") or {}
        questioned = self._load_evidence(roles.get("questioned"))
        fingerprint = self._load_evidence(roles.get("fingerprint"))

        parent_ids = meta.get("parent_evidence_ids") or []
        if isinstance(parent_ids, list) and len(parent_ids) >= 2:
            if not questioned:
                questioned = self._load_evidence(parent_ids[0])
            if not fingerprint:
                fingerprint = self._load_evidence(parent_ids[1])

        if questioned and fingerprint:
            return questioned, fingerprint

        job = self._load_job(meta.get("source_job_id"))
        if job:
            questioned = questioned or self._load_evidence(job.evidence_id)
            fp_id = (job.parameters or {}).get("fingerprint_id")
            fingerprint = fingerprint or self._load_evidence(fp_id)

        if not questioned:
            questioned = self._load_evidence(meta.get("parent_evidence_id"))
        return questioned, fingerprint

    def _edge_for_parent_child(
        self, parent: Evidence, child: Evidence, meta: dict[str, Any], role: str
    ) -> dict[str, Any]:
        params = dict(meta.get("parameters") or {})
        step = meta.get("derivation_step") or params.get("derivation_step") or ""
        technique = meta.get("technique")
        outputs = meta.get("derivation_outputs") or {}

        edge_params: dict[str, Any] = {**params, "role": role, "derivation_step": step}
        if meta.get("source_job_id"):
            edge_params["source_job_id"] = meta.get("source_job_id")
        if role in ("fingerprint_input", "fingerprint") and outputs:
            edge_params["outputs"] = {
                k: outputs[k]
                for k in (
                    "pce",
                    "p_value",
                    "p_fa",
                    "log10_p_fa",
                    "peak_location",
                    "peak_height",
                    "mode",
                    "sigma",
                )
                if k in outputs
            }

        procedure = self._procedure_for_edge(role, meta, child)
        edge: dict[str, Any] = {
            "from_evidence_id": str(parent.id),
            "to_evidence_id": str(child.id),
            "technique": technique,
            "parameters": edge_params,
            "procedure_summary": procedure,
        }
        if meta.get("source_job_id"):
            edge["source_job_id"] = meta.get("source_job_id")
        if meta.get("derivation_step"):
            edge["derivation_step"] = meta.get("derivation_step")
        return edge

    @staticmethod
    def _procedure_for_edge(role: str, meta: dict[str, Any], child: Evidence) -> str:
        if role == "reference_input":
            return "Referencia (padrao do sensor)"
        if role == "reference":
            return "Referencia estrutural (matriz)"
        if role == "lr_reference_population":
            return "Populacao LR (catalogo de referencia)"
        if role == "questioned":
            return "Evidencia questionada"
        if role in ("fingerprint_input", "fingerprint"):
            proc = meta.get("procedure_summary")
            if proc and "correlacao" in proc.lower():
                return proc
            return "Fingerprint PRNU (insumo)"
        step = meta.get("derivation_step") or ""
        if step == "fingerprint_aggregate":
            return meta.get("procedure_summary") or "Agregar fingerprint PRNU"
        if step == "correlation_surface_C":
            return meta.get("procedure_summary") or "Correlacao → superficie C"
        return meta.get("procedure_summary") or child.original_filename

    @staticmethod
    def _needs_legacy_provenance_upgrade(child: Evidence, meta: dict[str, Any]) -> bool:
        if meta.get("origin") != "derived":
            return False
        if meta.get("parent_inputs"):
            return False
        if meta.get("provenance_schema_version"):
            return meta.get("technique") == "prnu"
        return True

    def _inject_lr_reference_node(
        self,
        target: Evidence,
        nodes_map: dict[str, dict[str, Any]],
        edges: list[dict[str, Any]],
        edge_keys: set[tuple[str, str, str]],
    ) -> None:
        meta = target.extra_metadata or {}
        technique = meta.get("technique")
        if technique not in ("synthetic_image_detection", "sepael"):
            return
        outputs = meta.get("derivation_outputs") or {}
        pop_hash = outputs.get("reference_population_hash")
        pop_count = outputs.get("reference_population_count")
        if not pop_hash and not pop_count:
            ref_pop = (meta.get("parameters") or {}).get("reference_population")
            if isinstance(ref_pop, dict) and ref_pop.get("items"):
                from services.derivation_contract import reference_population_digest

                pop_hash = reference_population_digest(ref_pop)
                pop_count = len(ref_pop.get("items") or [])
        if not pop_hash and not pop_count:
            return

        node_id = f"synthetic:lr_population:{pop_hash or pop_count}"
        classifier = outputs.get("meta_classifier") or (meta.get("parameters") or {}).get("meta_classifier")
        augmented = outputs.get("use_augmented_reference")
        summary = f"Populacao LR · {pop_count or 0} subgrupo(s)"
        if classifier:
            summary += f" · meta {classifier}"
        if augmented:
            summary += " · augmentada"

        nodes_map.setdefault(
            node_id,
            {
                "evidence_id": node_id,
                "original_filename": "Populacao LR (catalogo)",
                "file_type": "referencia",
                "sha256": pop_hash or "",
                "is_derived": False,
                "is_synthetic": True,
                "synthetic_kind": "lr_reference_population",
                "procedure_summary": summary,
                "derivation_outputs": {
                    "reference_population_count": pop_count,
                    "reference_population_hash": pop_hash,
                    "meta_classifier": classifier,
                    "use_augmented_reference": augmented,
                },
            },
        )
        edge = {
            "from_evidence_id": node_id,
            "to_evidence_id": str(target.id),
            "technique": technique,
            "parameters": {
                "role": "lr_reference_population",
                "reference_population_hash": pop_hash,
                "reference_population_count": pop_count,
            },
            "procedure_summary": "Populacao LR (catalogo de referencia)",
            "derivation_step": meta.get("derivation_step"),
            "source_job_id": meta.get("source_job_id"),
        }
        key = (edge["from_evidence_id"], edge["to_evidence_id"], "lr_reference_population")
        if key not in edge_keys:
            edge_keys.add(key)
            edges.append(edge)

    def _collect_derivation_groups(self, target: Evidence) -> list[dict[str, Any]]:
        meta = target.extra_metadata or {}
        group_id = meta.get("derivation_group_id") or meta.get("source_job_id")
        if not group_id:
            return []
        rows = (
            self.db.query(Evidence)
            .filter(
                Evidence.case_id == target.case_id,
                Evidence.deleted_at.is_(None),
                Evidence.extra_metadata.isnot(None),
            )
            .all()
        )
        siblings: list[dict[str, Any]] = []
        for row in rows:
            if str(row.id) == str(target.id):
                continue
            row_meta = row.extra_metadata or {}
            if row_meta.get("origin") != "derived":
                continue
            row_group = row_meta.get("derivation_group_id") or row_meta.get("source_job_id")
            if str(row_group) != str(group_id):
                continue
            siblings.append(
                {
                    "evidence_id": str(row.id),
                    "original_filename": row.original_filename,
                    "artifact_role": row_meta.get("artifact_role"),
                    "derivation_step": row_meta.get("derivation_step"),
                    "artifact_filename": row_meta.get("artifact_filename"),
                }
            )
        if not siblings:
            return []
        siblings.sort(key=lambda item: str(item.get("original_filename") or ""))
        return [
            {
                "derivation_group_id": str(group_id),
                "source_job_id": meta.get("source_job_id"),
                "member_count": len(siblings) + 1,
                "siblings": siblings,
            }
        ]

    @staticmethod
    def _collect_legacy_notes(nodes: list[dict[str, Any]]) -> list[str]:
        notes: list[str] = []
        for node in nodes:
            if not node.get("legacy_provenance"):
                continue
            label = node.get("original_filename") or node.get("evidence_id")
            notes.append(
                f"Proveniencia legada em '{label}': parent_inputs ausente ou formato antigo PRNU; "
                "insumos reconstruidos por heuristica."
            )
        return notes

    @staticmethod
    def _assign_layers(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        if not nodes:
            return
        layer: dict[str, int] = {n["evidence_id"]: 0 for n in nodes}
        for e in edges:
            layer.setdefault(e["from_evidence_id"], 0)
            layer.setdefault(e["to_evidence_id"], 0)
        for _ in range(len(layer) + 1):
            changed = False
            for e in edges:
                u, v = e["from_evidence_id"], e["to_evidence_id"]
                if layer.get(u, 0) + 1 > layer.get(v, 0):
                    layer[v] = layer[u] + 1
                    changed = True
            if not changed:
                break
        for n in nodes:
            n["layer"] = layer.get(n["evidence_id"], 0)

    def _build_operations(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_child: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for e in edges:
            by_child[e["to_evidence_id"]].append(e)

        node_by_id = {n["evidence_id"]: n for n in nodes}
        operations: list[dict[str, Any]] = []

        for child_id, incoming in by_child.items():
            if len(incoming) < 2:
                continue
            child = node_by_id.get(child_id, {})
            step = ""
            for e in incoming:
                step = e.get("parameters", {}).get("derivation_step") or step
            label = child.get("procedure_summary") or ""
            outputs = child.get("derivation_outputs")
            for e in incoming:
                outs = e.get("parameters", {}).get("outputs")
                if outs:
                    outputs = outs
                if e.get("procedure_summary") and "correlacao" in (e.get("procedure_summary") or "").lower():
                    label = e["procedure_summary"]
            if not label:
                label = f"Operacao ({step or 'derivacao'})"

            input_count = len(incoming)
            images_used = child.get("images_used")
            if step == "fingerprint_aggregate":
                n = images_used if images_used is not None else input_count
                label = f"{label} · {n} imagem(ns) de referencia"
            elif input_count >= 2:
                label = f"{label} · {input_count} insumos"

            operations.append(
                {
                    "id": f"op-{child_id}-{step or 'merge'}",
                    "to_evidence_id": child_id,
                    "derivation_step": step,
                    "label": label,
                    "input_count": input_count,
                    "images_used": images_used,
                    "inputs": [
                        {
                            "evidence_id": e["from_evidence_id"],
                            "role": e.get("parameters", {}).get("role"),
                            "label": e.get("procedure_summary"),
                        }
                        for e in incoming
                    ],
                    "outputs": outputs,
                }
            )
        return operations

    @staticmethod
    def _build_phases(nodes: list[dict[str, Any]], operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not nodes:
            return []
        max_layer = max(n.get("layer", 0) for n in nodes)
        op_steps = {op.get("derivation_step") for op in operations if op.get("derivation_step")}

        phases: list[dict[str, Any]] = []
        for layer_idx in range(max_layer + 1):
            layer_nodes = [n for n in nodes if n.get("layer") == layer_idx]
            if not layer_nodes:
                continue
            if layer_idx == 0 and all(not n.get("is_derived") for n in layer_nodes):
                label = "Insumos originais / referencias"
            elif any(n.get("artifact_role") == "prnu_fingerprint" for n in layer_nodes):
                label = "Fingerprint PRNU (padrao agregado)"
            elif any(n.get("derivation_step") == "correlation_surface_C" for n in layer_nodes):
                label = "Superficie C (resultado)"
            elif "fingerprint_aggregate" in op_steps and layer_idx < max_layer:
                label = f"Camada {layer_idx + 1}"
            else:
                label = f"Camada {layer_idx + 1}"

            phases.append(
                {
                    "layer": layer_idx,
                    "label": label,
                    "node_ids": [n["evidence_id"] for n in layer_nodes],
                    "node_count": len(layer_nodes),
                }
            )
        return phases

    @staticmethod
    def extract_prnu_job_outputs(job_result: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "pce",
            "p_value",
            "p_fa",
            "log10_p_fa",
            "peak_location",
            "peak_height",
            "pce_no_crop",
            "mode",
            "sigma",
            "best_scale",
        )
        return {k: job_result[k] for k in keys if k in job_result}

    @staticmethod
    def build_prnu_correlation_metadata(
        job: AnalysisJob,
        parent_evidences: list[tuple[Evidence, str]],
        artifact_filename: str,
        label: str | None,
        job_result: dict[str, Any],
    ) -> dict[str, Any]:
        from services.derivation_contract import build_derivation_metadata, parent_ref_from_evidence

        params = dict(job.parameters or {})
        outputs = DerivationLineageBuilder.extract_prnu_job_outputs(job_result)

        parents = [
            parent_ref_from_evidence(
                ev,
                role,
                "Evidencia questionada" if role == "questioned" else "Fingerprint PRNU",
            )
            for ev, role in parent_evidences
        ]

        mode = params.get("mode", "full")
        sigma = params.get("sigma")
        procedure = f"PRNU correlacao · superficie C · modo {mode}"
        if sigma is not None:
            procedure += f" · σ={sigma}"
        if outputs.get("pce") is not None:
            procedure += f" · PCE={outputs['pce']}"

        return build_derivation_metadata(
            parents=parents,
            technique="prnu",
            derivation_step="correlation_surface_C",
            procedure_summary=procedure,
            parameters=params,
            artifact_role="prnu_correlation_surface",
            artifact_filename=artifact_filename,
            derivation_outputs=outputs,
            source_job_id=str(job.id),
            label=label,
        )
