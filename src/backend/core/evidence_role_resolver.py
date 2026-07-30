"""Resolve evidence-role parameters into paths/labels before plugin execution."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.evidence_role_overrides import resolve_evidence_schema
from models.evidence import Evidence


class EvidenceRoleResolver:
    """Scan plugin parameters_schema for x-forensic-role annotations and resolve IDs."""

    def __init__(self, db: Session):
        self.db = db

    def _resolve_evidence(
        self,
        ev_id: Any,
        *,
        expected_file_type: str | None = None,
        extra_validator: callable | None = None,
    ) -> tuple[str, str]:
        try:
            ev_uuid = ev_id if isinstance(ev_id, uuid.UUID) else uuid.UUID(str(ev_id))
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"ID de evidencia invalido: {ev_id}",
            )
        ev = self.db.query(Evidence).filter(
            Evidence.id == ev_uuid,
            Evidence.deleted_at.is_(None),
        ).first()
        if not ev:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Evidencia nao encontrada: {ev_id}",
            )
        if expected_file_type and ev.file_type != expected_file_type:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Evidencia {ev.original_filename} nao e do tipo {expected_file_type}"
                ),
            )
        if extra_validator:
            extra_validator(ev)
        return ev.file_path, ev.original_filename or ev.filename

    def _resolve_list(
        self,
        ev_ids: list[Any],
        *,
        expected_file_type: str | None = None,
        extra_validator: callable | None = None,
    ) -> tuple[list[str], list[str]]:
        paths: list[str] = []
        labels: list[str] = []
        for ev_id in ev_ids or []:
            path, label = self._resolve_evidence(
                ev_id,
                expected_file_type=expected_file_type,
                extra_validator=extra_validator,
            )
            paths.append(path)
            labels.append(label)
        return paths, labels

    def _resolve_fingerprint(self, case_id: Any, fingerprint_id: Any) -> str:
        if not case_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Parametros invalidos: case_id obrigatorio com fingerprint_id",
            )
        try:
            case_uuid = case_id if isinstance(case_id, uuid.UUID) else uuid.UUID(str(case_id))
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Parametros invalidos: case_id invalido",
            )
        from services.prnu_fingerprint_service import resolve_fingerprint_path

        return str(resolve_fingerprint_path(self.db, case_uuid, str(fingerprint_id)))

    def resolve(
        self,
        parameters: dict[str, Any],
        parameters_schema: dict[str, Any] | None,
        technique: str | None = None,
    ) -> dict[str, Any]:
        """Return a new parameters dict with evidence roles resolved."""
        effective_schema = resolve_evidence_schema(technique, parameters_schema)
        if not effective_schema:
            return dict(parameters)

        resolved = dict(parameters)
        properties = effective_schema.get("properties") or {}

        for param_name, schema in properties.items():
            if not isinstance(schema, dict):
                continue
            role = schema.get("x-forensic-role")
            if not role:
                continue

            value = resolved.get(param_name)
            if value is None:
                continue

            media_type = schema.get("x-forensic-media")
            is_multiple = schema.get("x-forensic-multiple") is True or schema.get("type") == "array"

            expected_type = self._map_media_type(media_type)

            base_name = self._strip_id_suffix(param_name)

            if role == "fingerprint":
                resolved[f"{base_name}_path"] = self._resolve_fingerprint(
                    resolved.get("case_id"), value
                )
                continue

            if is_multiple:
                paths, labels = self._resolve_list(
                    value if isinstance(value, list) else [value],
                    expected_file_type=expected_type,
                )
                resolved[f"{base_name}_paths"] = paths
                resolved[f"{base_name}_labels"] = labels
            else:
                path, label = self._resolve_evidence(
                    value,
                    expected_file_type=expected_type,
                )
                resolved[f"{base_name}_path"] = path
                resolved[f"{base_name}_label"] = label

        return resolved

    @staticmethod
    def _strip_id_suffix(param_name: str) -> str:
        """Return base name for resolved path/label keys.

        reference_evidence_id   -> reference
        questioned_evidence_ids -> questioned
        evidence_ids            -> evidence
        fingerprint_id          -> fingerprint
        """
        if param_name.endswith("_evidence_ids"):
            return param_name[:-13]
        if param_name.endswith("_evidence_id"):
            return param_name[:-12]
        if param_name.endswith("_ids"):
            return param_name[:-4]
        if param_name.endswith("_id"):
            return param_name[:-3]
        return param_name

    @staticmethod
    def _map_media_type(media_type: str | None) -> str | None:
        mapping = {
            "imagem": "imagem",
            "image": "imagem",
            "audio": "audio",
            "video": "video",
            "pdf": "pdf",
        }
        return mapping.get(media_type) if media_type else None


def resolve_evidence_parameters(
    db: Session,
    parameters: dict[str, Any],
    parameters_schema: dict[str, Any] | None,
    technique: str | None = None,
) -> dict[str, Any]:
    """Convenience wrapper around EvidenceRoleResolver."""
    return EvidenceRoleResolver(db).resolve(parameters, parameters_schema, technique=technique)
