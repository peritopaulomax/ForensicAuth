"""Gera pacote ZIP Peritus a partir de caso ForensicAuth (XML estrutural, sem assinatura ICP)."""

from __future__ import annotations

import base64
import hashlib
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from sqlalchemy.orm import Session

from models.analysis_job import AnalysisJob
from models.case import Case
from models.evidence import Evidence
from services.peritus_file_meta import infer_file_type
from services.peritus_xml import PERITUS_XML_NAME

NS_FORENSIC_AUTH_TECHNIQUE = "forensicauth"


def hex_sha256_to_peritus_b64(hex_val: str) -> str:
    return base64.urlsafe_b64encode(bytes.fromhex(hex_val)).decode().rstrip("=")


def _brace_uuid(value: uuid.UUID | str) -> str:
    return "{" + str(value).lower() + "}"


def _evidence_origin(ev: Evidence) -> str:
    meta = ev.extra_metadata or {}
    return meta.get("origin", "upload")


def _peritus_folder_for_evidence(ev: Evidence) -> str:
    meta = ev.extra_metadata or {}
    path = meta.get("peritus_path")
    if isinstance(path, str) and "/" in path:
        return path.rsplit("/", 1)[0]
    if _evidence_origin(ev) == "derived":
        return "derived-files"
    return "ForensicAuth"


def _archive_path_for_evidence(ev: Evidence) -> str:
    meta = ev.extra_metadata or {}
    if isinstance(meta.get("peritus_path"), str):
        return meta["peritus_path"].replace("\\", "/")
    folder = _peritus_folder_for_evidence(ev)
    return f"{folder}/{ev.original_filename}"


def _build_case_info_xml(case: Case) -> str:
    fields = [
        ("PROCEDIMENTO", "Numero do Procedimento", case.protocol_number or ""),
        ("EXAME", "Tipo de Exame", case.title or "ForensicAuth"),
    ]
    if case.description:
        fields.append(("DESCRICAO", "Descricao", case.description[:500]))

    parts = ['        <peritusCaseInfo>']
    for field_id, name, value in fields:
        parts.append(
            f'            <input type="text" id="{escape(field_id)}" '
            f'name="{escape(name)}" value="{escape(str(value))}" />'
        )
    parts.append("        </peritusCaseInfo>")
    return "\n".join(parts)


def _build_evidence_xml(ev: Evidence, archive_path: str) -> str:
    hash_b64 = hex_sha256_to_peritus_b64(ev.sha256)
    mime = ev.mime_type or "application/octet-stream"
    ev_uuid = ev.extra_metadata.get("peritus_uuid") if ev.extra_metadata else None
    uid = _brace_uuid(ev_uuid or ev.id)
    tag = "derivedEvidence" if _evidence_origin(ev) == "derived" else "evidence"
    inner = "derivedEvidence" if tag == "derivedEvidence" else "evidence"
    return f"""                <{inner}>
                    <uuid>{uid}</uuid>
                    <name>{escape(ev.original_filename)}</name>
                    <mimeType>{escape(mime)}</mimeType>
                    <path>{escape(archive_path)}</path>
                    <hash alg="Sha256">{hash_b64}</hash>
                </{inner}>"""


def _build_calculation_xml(job: AnalysisJob, output_ev: Evidence) -> str:
    op = f"{NS_FORENSIC_AUTH_TECHNIQUE}:{job.technique}"
    out_uuid = _brace_uuid(output_ev.id)
    in_uuid = _brace_uuid(job.evidence_id)
    return f"""                <calculation>
                    <operationSignature>{escape(op)}</operationSignature>
                    <operationVersion>1</operationVersion>
                    <inputs>
                        <input name="input">
                            <file ref="{in_uuid}" />
                        </input>
                    </inputs>
                    <parameters>
                        <param name="technique">{escape(job.technique)}</param>
                    </parameters>
                    <output file ref="{out_uuid}" />
                </calculation>"""


def build_peritus_xml(case: Case, evidences: list[Evidence], jobs: list[AnalysisJob]) -> str:
    uploads = [e for e in evidences if _evidence_origin(e) != "derived"]
    derived = [e for e in evidences if _evidence_origin(e) == "derived"]

    ev_xml = "\n".join(
        _build_evidence_xml(ev, _archive_path_for_evidence(ev)) for ev in uploads
    )
    der_xml = "\n".join(
        _build_evidence_xml(ev, _archive_path_for_evidence(ev)) for ev in derived
    )

    job_by_output = {str(j.result_sha256): j for j in jobs if j.result_sha256}
    calc_xml_parts: list[str] = []
    for dev in derived:
        job = job_by_output.get(dev.sha256)
        if job:
            calc_xml_parts.append(_build_calculation_xml(job, dev))
    calc_xml = "\n".join(calc_xml_parts)

    exported_at = datetime.now(timezone.utc).isoformat()
    info = _build_case_info_xml(case)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<peritus>
    <peritusCase version="1">
        <isWrappedAndLocked>false</isWrappedAndLocked>
{info}
        <medias />
        <evidences>
{ev_xml}
        </evidences>
        <derivedEvidences>
{der_xml}
        </derivedEvidences>
        <calculations>
{calc_xml}
        </calculations>
        <!-- Exportado pelo ForensicAuth em {escape(exported_at)}; requer assinatura ICP no Peritus -->
    </peritusCase>
</peritus>
"""


def build_peritus_zip_from_case(
    db: Session,
    case: Case,
    output_path: Path,
    *,
    workspace: Path | None = None,
) -> Path:
    """Empacota caso VA (ou Peritus+VA) em ZIP legivel pelo Peritus (sem assinatura)."""
    evidences = (
        db.query(Evidence)
        .filter(Evidence.case_id == case.id, Evidence.deleted_at.is_(None))
        .all()
    )
    evidence_ids = [e.id for e in evidences]
    jobs: list[AnalysisJob] = []
    if evidence_ids:
        jobs = (
            db.query(AnalysisJob)
            .filter(
                AnalysisJob.evidence_id.in_(evidence_ids),
                AnalysisJob.status == "completed",
            )
            .all()
        )

    xml = build_peritus_xml(case, evidences, jobs)

    staging = output_path.parent / f"_peritus_staging_{case.id}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    (staging / PERITUS_XML_NAME).write_text(xml, encoding="utf-8")

    for ev in evidences:
        src = Path(ev.file_path)
        if not src.is_file():
            continue
        arc = _archive_path_for_evidence(ev)
        dest = staging / arc
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(staging).as_posix())

    shutil.rmtree(staging, ignore_errors=True)
    return output_path
