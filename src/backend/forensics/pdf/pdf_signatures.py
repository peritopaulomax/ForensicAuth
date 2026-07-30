"""Integração ForensicAuth do motor pdfsig_forense (relatório PAdES/ICP-Brasil).

Artefatos gerados em ``out_dir``:
  - signatures_report.txt  (relatório Markdown humanizado)
  - signatures.json        (dados estruturados)
  - signatures/certs/*.pem (certificados colhidos no arquivo)
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence

from asn1crypto import pem

LOG = logging.getLogger(__name__)


def _resolve_trust_anchor_paths(
    explicit: Optional[Sequence[str]] = None,
    *,
    anchor_dir: Optional[str] = None,
) -> List[str]:
    paths: List[str] = []
    for item in explicit or []:
        if not item:
            continue
        for part in str(item).replace(";", ",").split(","):
            p = part.strip()
            if p:
                paths.append(p)

    if anchor_dir:
        root = Path(anchor_dir)
        if root.is_dir():
            for pattern in ("*.crt", "*.pem", "*.cer", "*.der", "*.p7b", "*.p7c"):
                for f in sorted(root.glob(pattern)):
                    if f.is_file() and f.name.upper() != "README.MD":
                        paths.append(str(f))
    # dedupe preserving order
    seen = set()
    out: List[str] = []
    for p in paths:
        key = str(Path(p).resolve()) if Path(p).exists() else p
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _options_from_settings() -> Any:
    from forensics.pdf import pdfsig_forense as eng

    try:
        from app.config import get_settings

        settings = get_settings()
    except Exception:
        settings = SimpleNamespace(
            PDF_SIG_TRUST_ANCHORS="",
            PDF_SIG_TRUST_ANCHOR_DIR="",
            PDF_SIG_TZ_OFFSET=-3.0,
            PDF_SIG_FETCH=False,
            PDF_SIG_REDACT=True,
        )

    explicit = []
    raw = getattr(settings, "PDF_SIG_TRUST_ANCHORS", "") or ""
    if raw:
        explicit = [p.strip() for p in str(raw).replace(";", ",").split(",") if p.strip()]

    anchor_dir = getattr(settings, "PDF_SIG_TRUST_ANCHOR_DIR", "") or ""
    if not anchor_dir:
        # default convention under MODELS_DIR
        models = getattr(settings, "MODELS_DIR", "") or ""
        if models:
            candidate = Path(models) / "icpbrasil"
            if candidate.is_dir():
                anchor_dir = str(candidate)

    trust_paths = _resolve_trust_anchor_paths(explicit, anchor_dir=anchor_dir or None)
    tz = getattr(settings, "PDF_SIG_TZ_OFFSET", -3.0)
    try:
        tz_f = float(tz) if tz is not None else -3.0
    except (TypeError, ValueError):
        tz_f = -3.0

    return eng.AnalysisOptions(
        trust_anchors=trust_paths,
        fetch=bool(getattr(settings, "PDF_SIG_FETCH", False)),
        redact=bool(getattr(settings, "PDF_SIG_REDACT", True)),
        tz=tz_f,
    )


def _dump_cert_pems(harvest: Any, certs_dir: Path) -> List[Dict[str, str]]:
    certs_dir.mkdir(parents=True, exist_ok=True)
    catalog: List[Dict[str, str]] = []
    from forensics.pdf.pdfsig_forense import cn_of, fp

    for idx, cert in enumerate(harvest.cert_list, start=1):
        cn = cn_of(cert)
        safe_cn = "".join(ch if ch.isalnum() else "_" for ch in cn)[:50] or f"cert{idx}"
        name = f"sig_harvest_{idx:02d}_{safe_cn}.pem"
        path = certs_dir / name
        path.write_bytes(pem.armor("CERTIFICATE", cert.dump()))
        catalog.append(
            {
                "cn": cn,
                "sha256": fp(cert),
                "pem_path": f"signatures/certs/{name}",
                "origin": harvest.cert_origin(cert),
            }
        )
    return catalog


def analyze_pdf_signatures(pdf_path: str, out_dir: Path) -> Dict[str, Any]:
    """
    Analisa assinaturas digitais do PDF com o motor pdfsig_forense.

    Compatível com o pipeline ``pdf_forensic_extract`` (grava report + JSON).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    certs_dir = out_dir / "signatures" / "certs"
    certs_dir.mkdir(parents=True, exist_ok=True)

    result: Dict[str, Any] = {
        "signed": False,
        "signature_count": 0,
        "status": "ok",
        "message": "",
        "engine": "pdfsig_forense",
        "trust_disclaimer": (
            "Prefira ancorar a validacao na raiz oficial ICP-Brasil (ITI) via "
            "PDF_SIG_TRUST_ANCHORS ou models/icpbrasil/. Sem isso, o motor usa "
            "raizes autoassinadas do proprio arquivo e marca circularidade. "
            "Este relatório nao substitui validar.iti.gov.br."
        ),
        "anchors_from_file": False,
        "anchor_mode": "",
        "findings_summary": {"CRITICO": 0, "ALERTA": 0, "ATENCAO": 0, "OK": 0, "INFO": 0},
        "signatures": [],
        "errors": [],
        "timestamp": None,
    }

    try:
        from forensics.pdf import pdfsig_forense as eng
    except ImportError as exc:
        result["status"] = "unavailable"
        result["message"] = f"Motor pdfsig_forense indisponivel: {exc}"
        _write_fallback(out_dir, result)
        return result

    options = _options_from_settings()
    options.dump_material_dir = str(out_dir / "signatures" / "material")

    try:
        analysis = eng.analyze_pdf_file(str(pdf_path), options)
    except Exception as exc:
        LOG.exception("Falha na analise pdfsig_forense")
        result["status"] = "error"
        result["message"] = f"Erro ao analisar assinaturas: {exc}"
        result["errors"].append(str(exc))
        _write_fallback(out_dir, result)
        return result

    pem_catalog = _dump_cert_pems(analysis.harvest, certs_dir)

    summary = {"CRITICO": 0, "ALERTA": 0, "ATENCAO": 0, "OK": 0, "INFO": 0}
    for f in analysis.findings:
        sev = getattr(f, "severity", None) or "INFO"
        summary[sev] = summary.get(sev, 0) + 1

    # Compact signature summaries for plugin/UI
    sig_summaries: List[Dict[str, Any]] = []
    for s in analysis.sigs:
        if getattr(s, "obj_type", None) == "/DocTimeStamp":
            continue
        human = {
            "headline": None,
            "integrity_label": "Íntegra" if s.digest_ok else (
                "Comprometida" if s.digest_ok is False else "Não apurada"
            ),
            "crypto_label": "Válida" if s.math_ok else (
                "Inválida" if s.math_ok is False else "Não apurada"
            ),
            "chain_label": s.pades_level or "",
            "timestamp_label": (
                eng.fmt_dt(s.timestamps[0].gen_time, options.tz)
                if s.timestamps else "Ausente"
            ),
            "revocation_label": (
                "Revogado"
                if (s.revocation or {}).get("revoked")
                else (
                    "Não revogado"
                    if (s.revocation or {}).get("checked")
                    else "Sem evidência embutida / não apurado"
                )
            ),
            "pades_label": s.pades_level or "",
        }
        if s.digest_ok and s.math_ok:
            human["headline"] = (
                f"Assinatura do campo `{s.field_name}` tecnicamente consistente "
                f"(PAdES {s.pades_level or '—'})."
            )
        elif s.digest_ok is False or s.math_ok is False:
            human["headline"] = (
                f"Assinatura `{s.field_name}` com falha criptográfica "
                "(não use como prova de integridade sem perícia)."
            )
        else:
            human["headline"] = f"Assinatura `{s.field_name}` com resultado indeterminado."

        signer_cn = None
        if s.signer_info:
            signer_cn = (s.signer_info.get("subject") or "").split(";")[0]
        elif s.signer_cert is not None:
            signer_cn = eng.cn_of(s.signer_cert)

        sig_summaries.append(
            {
                "index": s.index,
                "field_name": s.field_name,
                "obj_type": s.obj_type,
                "digest_ok": s.digest_ok,
                "sig_ok": s.math_ok,
                "pades_level": s.pades_level,
                "pades_note": s.pades_note,
                "signer_cn": signer_cn,
                "human_verdict": human,
                "findings": [
                    {
                        "severity": f.severity,
                        "code": f.code,
                        "title": f.title,
                        "detail": f.detail,
                    }
                    for f in (s.findings or [])
                ],
            }
        )

    payload = analysis.payload
    payload["signed"] = analysis.signed
    payload["signature_count"] = analysis.signature_count
    payload["status"] = "ok" if analysis.signed or analysis.signature_count == 0 else "ok"
    if not analysis.signed and analysis.signature_count == 0:
        payload["status"] = "unsigned"
    payload["message"] = (
        f"{analysis.signature_count} assinatura(s) encontrada(s)."
        if analysis.signed
        else "Nenhuma assinatura digital embutida encontrada."
    )
    payload["engine"] = f"pdfsig_forense v{eng.VERSION}"
    payload["trust_disclaimer"] = result["trust_disclaimer"]
    payload["anchors_from_file"] = analysis.anchors_from_file
    payload["anchor_mode"] = analysis.anchor_mode_label
    payload["findings_summary"] = summary
    payload["signatures_ui"] = sig_summaries
    payload["cert_pem_catalog"] = pem_catalog
    payload["timestamp"] = eng.fmt_dt(
        __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        options.tz,
    )

    # Persist artifacts
    report_path = out_dir / "signatures_report.txt"
    report_path.write_text(analysis.markdown, encoding="utf-8")
    # Also keep .md alias for clarity when saving derivatives
    (out_dir / "signatures_report.md").write_text(analysis.markdown, encoding="utf-8")

    import json

    json_path = out_dir / "signatures.json"
    json_path.write_text(
        json.dumps(eng.to_jsonable(payload), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    result.update(
        {
            "signed": analysis.signed,
            "signature_count": analysis.signature_count,
            "status": payload["status"],
            "message": payload["message"],
            "anchors_from_file": analysis.anchors_from_file,
            "anchor_mode": analysis.anchor_mode_label,
            "findings_summary": summary,
            "signatures": sig_summaries,
            "document_dss": {
                "present": bool(getattr(analysis.dss, "present", False)),
                "cert_count": int(getattr(analysis.dss, "n_certs", 0) or 0),
                "crl_count": int(getattr(analysis.dss, "n_crls", 0) or 0),
                "ocsp_count": int(getattr(analysis.dss, "n_ocsps", 0) or 0),
                "vri_count": len(getattr(analysis.dss, "vri_keys", []) or []),
            },
            "has_critical": analysis.has_critical,
            "timestamp": payload["timestamp"],
            "markdown_report": True,
        }
    )
    return result


def _write_fallback(out_dir: Path, result: Dict[str, Any]) -> None:
    import json
    from datetime import datetime, timezone

    result.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    (out_dir / "signatures.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    lines = [
        "# Relatório técnico: assinaturas digitais em PDF",
        "",
        f"**Status:** {result.get('status')}",
        f"**Mensagem:** {result.get('message')}",
        "",
    ]
    for e in result.get("errors") or []:
        lines.append(f"- Erro: {e}")
    text = "\n".join(lines) + "\n"
    (out_dir / "signatures_report.txt").write_text(text, encoding="utf-8")
    (out_dir / "signatures_report.md").write_text(text, encoding="utf-8")
