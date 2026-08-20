"""Dependentes de derivacao: quais derivados ativos consomem um conjunto de evidencias."""

from __future__ import annotations

import uuid
from typing import Any, Iterable

from sqlalchemy.orm import Session

from models.evidence import Evidence
from services.derivation_lineage import DerivationLineageBuilder
from services.evidence_classification import is_derived


def _as_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _group_key(evidence: Evidence) -> str:
    meta = evidence.extra_metadata or {}
    return str(meta.get("derivation_group_id") or meta.get("source_job_id") or evidence.id)


def _descriptor(evidence: Evidence) -> dict[str, Any]:
    meta = evidence.extra_metadata or {}
    return {
        "evidence_id": str(evidence.id),
        "original_filename": evidence.original_filename,
        "file_type": evidence.file_type,
        "is_derived": is_derived(evidence),
        "technique": meta.get("technique"),
        "artifact_role": meta.get("artifact_role"),
        "derivation_group_id": _group_key(evidence),
    }


class EvidenceDependentsResolver:
    """Indice reverso insumo -> derivado, com fecho transitivo dos dependentes exclusivos."""

    def __init__(self, db: Session):
        self.db = db
        self.lineage = DerivationLineageBuilder(db)

    def _active_case_evidences(self, case_id: uuid.UUID) -> list[Evidence]:
        return (
            self.db.query(Evidence)
            .filter(Evidence.case_id == case_id, Evidence.deleted_at.is_(None))
            .order_by(Evidence.created_at.asc())
            .all()
        )

    def dependent_derivatives(
        self,
        case_id: uuid.UUID,
        target_ids: Iterable[uuid.UUID | str],
    ) -> list[dict[str, Any]]:
        """Derivados ativos que consomem algum alvo (direta ou transitivamente).

        `exclusive=True` quando todos os insumos ativos do derivado estao no escopo de
        exclusao — unico caso elegivel a cascade. Derivados que tambem dependem de
        insumos preservados retornam `exclusive=False` e os nomes em `retained_parents`.
        """
        targets: set[str] = set()
        for tid in target_ids:
            parsed = _as_uuid(tid)
            if parsed is not None:
                targets.add(str(parsed))
        if not targets:
            return []

        evidences = self._active_case_evidences(case_id)
        derivatives = [ev for ev in evidences if is_derived(ev) and str(ev.id) not in targets]
        if not derivatives:
            return []

        parents_by_derivative: dict[str, list[tuple[Evidence, str]]] = {
            str(ev.id): self.lineage.resolve_parents(ev) for ev in derivatives
        }

        in_scope = set(targets)
        affected: set[str] = set()

        changed = True
        while changed:
            changed = False
            for derivative in derivatives:
                did = str(derivative.id)
                parent_ids = {str(parent.id) for parent, _role in parents_by_derivative[did]}
                if not parent_ids & in_scope:
                    continue
                if did not in affected:
                    affected.add(did)
                    changed = True
                if parent_ids.issubset(in_scope) and did not in in_scope:
                    in_scope.add(did)
                    changed = True

        records: list[dict[str, Any]] = []
        for derivative in derivatives:
            did = str(derivative.id)
            if did not in affected:
                continue
            parents = parents_by_derivative[did]
            records.append(
                {
                    **_descriptor(derivative),
                    "exclusive": did in in_scope,
                    "parents": [
                        {
                            "evidence_id": str(parent.id),
                            "role": role,
                            "original_filename": parent.original_filename,
                            "in_scope": str(parent.id) in in_scope,
                        }
                        for parent, role in parents
                    ],
                    "retained_parents": [
                        parent.original_filename
                        for parent, _role in parents
                        if str(parent.id) not in in_scope
                    ],
                }
            )

        return sorted(
            records,
            key=lambda item: (
                not item["exclusive"],
                item["derivation_group_id"],
                item["original_filename"],
            ),
        )

    def deletion_plan(
        self,
        case_id: uuid.UUID,
        target_ids: Iterable[uuid.UUID | str],
        include_dependent_derivatives: bool,
    ) -> dict[str, Any]:
        """Alvos + dependentes, separando o que o cascade removeria do que fica retido."""
        ids = [tid for tid in (_as_uuid(t) for t in target_ids) if tid is not None]
        dependents = self.dependent_derivatives(case_id, ids)
        cascade = [d for d in dependents if d["exclusive"]] if include_dependent_derivatives else []
        return {
            "target_ids": [str(tid) for tid in ids],
            "dependents": dependents,
            "cascade_ids": [d["evidence_id"] for d in cascade],
            "retained_dependents": [d for d in dependents if not d["exclusive"]],
        }

    def preview(
        self,
        case_id: uuid.UUID,
        targets: list[Evidence],
    ) -> dict[str, Any]:
        """Payload de impacto para confirmacao de exclusao."""
        dependents = self.dependent_derivatives(case_id, [ev.id for ev in targets])
        exclusive = [d for d in dependents if d["exclusive"]]
        return {
            "case_id": str(case_id),
            "targets": [_descriptor(ev) for ev in targets],
            "dependents": dependents,
            "dependent_count": len(dependents),
            "cascade_count": len(exclusive),
            "retained_count": len(dependents) - len(exclusive),
            "package_count": len({d["derivation_group_id"] for d in exclusive}),
        }
